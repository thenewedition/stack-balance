"use strict";

import { api } from "../api.js";
import { el, toast, openModal, confirmModal, field, checkbox, select } from "../dom.js";
import { fmt, parseDollars, centsToInput, today } from "../format.js";
import * as refdata from "../refdata.js";

const PAGE_SIZE = 50;
const state = { page: 0, filters: {} };

export async function render(host) {
  await refdata.load(true);
  host.replaceChildren(el("div", { class: "empty", text: "Loading…" }));
  await draw(host);
}

function filterParams() {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(state.filters)) {
    if (value !== "" && value !== null && value !== undefined) params.set(key, value);
  }
  params.set("limit", String(PAGE_SIZE + 1));  // +1 to detect a next page
  params.set("offset", String(state.page * PAGE_SIZE));
  return params.toString();
}

async function draw(host) {
  const rows = await api.get("/transactions?" + filterParams());
  const hasNext = rows.length > PAGE_SIZE;
  const txns = rows.slice(0, PAGE_SIZE);
  const selected = new Set();

  /* ----- filters ----- */
  const accountFilter = select(
    [{ value: "", label: "All accounts" },
     ...refdata.activeAccounts().map(a => ({ value: a.id, label: a.name }))],
    state.filters.account_id ?? "");
  const categoryFilter = select(
    [{ value: "", label: "All categories" }, ...refdata.allCategoryOptions()],
    state.filters.category_id ?? "");
  const startInput = el("input", { type: "date", value: state.filters.start_date ?? "" });
  const endInput = el("input", { type: "date", value: state.filters.end_date ?? "" });
  const payeeInput = el("input", { type: "search", placeholder: "Search payee…",
    value: state.filters.payee ?? "" });
  const clearedFilter = select(
    [{ value: "", label: "Any status" }, { value: "true", label: "Cleared" },
     { value: "false", label: "Uncleared" }],
    state.filters.cleared ?? "");

  const applyFilters = () => {
    state.filters = {
      account_id: accountFilter.value, category_id: categoryFilter.value,
      start_date: startInput.value, end_date: endInput.value,
      payee: payeeInput.value.trim(), cleared: clearedFilter.value,
    };
    state.page = 0;
    draw(host);
  };
  for (const control of [accountFilter, categoryFilter, startInput, endInput, clearedFilter]) {
    control.addEventListener("change", applyFilters);
  }
  payeeInput.addEventListener("keydown", (event) => { if (event.key === "Enter") applyFilters(); });

  const addButton = el("button", { class: "primary", text: "Add transaction" });
  addButton.addEventListener("click", () => editorModal(null, () => draw(host)));

  const filters = el("div", { class: "filters" },
    el("label", {}, "Account", accountFilter),
    el("label", {}, "Category", categoryFilter),
    el("label", {}, "From", startInput),
    el("label", {}, "To", endInput),
    el("label", {}, "Payee", payeeInput),
    el("label", {}, "Status", clearedFilter),
    el("span", { class: "spacer", style: "flex:1" }),
    addButton);

  /* ----- table ----- */
  const selectAll = el("input", { type: "checkbox", "aria-label": "Select all" });
  const body = el("tbody");
  const rowChecks = [];

  const updateBulkbar = () => {
    bulkCount.textContent = `${selected.size} selected`;
    bulkbar.style.display = selected.size ? "flex" : "none";
    selectAll.checked = selected.size === txns.length && txns.length > 0;
  };

  selectAll.addEventListener("change", () => {
    selected.clear();
    if (selectAll.checked) txns.forEach(t => selected.add(t.id));
    rowChecks.forEach(cb => (cb.checked = selectAll.checked));
    updateBulkbar();
  });

  for (const txn of txns) {
    const check = el("input", { type: "checkbox", "aria-label": `Select transaction ${txn.id}` });
    check.addEventListener("change", () => {
      check.checked ? selected.add(txn.id) : selected.delete(txn.id);
      updateBulkbar();
    });
    rowChecks.push(check);

    const categoryCell = el("td");
    if (txn.splits.length > 1) {
      categoryCell.append(el("span", { class: "split-badge", text: "split" }),
        document.createTextNode(txn.splits.map(s =>
          `${refdata.categoryName(s.category_id)} ${fmt(s.amount_cents)}`).join(" · ")));
    } else {
      categoryCell.textContent = refdata.categoryName(txn.splits[0]?.category_id);
    }

    const clearedCell = el("td", { class: "clickable", title: "Click to toggle cleared",
      text: txn.cleared ? "✓" : "○" });
    clearedCell.addEventListener("click", async () => {
      try {
        await api.patch(`/transactions/${txn.id}`, { cleared: !txn.cleared });
        txn.cleared = !txn.cleared;
        clearedCell.textContent = txn.cleared ? "✓" : "○";
      } catch (error) { toast(error.message); }
    });

    const editButton = el("button", { class: "icon", text: "Edit" });
    editButton.addEventListener("click", () => editorModal(txn, () => draw(host)));

    body.append(el("tr", {},
      el("td", {}, check),
      el("td", { text: txn.date }),
      el("td", { text: refdata.accountName(txn.account_id) }),
      el("td", { text: txn.payee || "—" }),
      categoryCell,
      el("td", { class: "muted", text: txn.memo }),
      el("td", { class: "num" + (txn.amount_cents < 0 ? " neg" : ""), text: fmt(txn.amount_cents) }),
      clearedCell,
      el("td", {}, editButton)));
  }

  const table = el("div", { class: "table-scroll" }, el("table", {},
    el("thead", {}, el("tr", {},
      el("th", {}, selectAll), el("th", { text: "Date" }), el("th", { text: "Account" }),
      el("th", { text: "Payee" }), el("th", { text: "Category" }), el("th", { text: "Memo" }),
      el("th", { class: "num", text: "Amount" }), el("th", { text: "Cleared" }), el("th"))),
    body));

  /* ----- pager ----- */
  const prevPage = el("button", { class: "icon", text: "◀ Prev" });
  const nextPage = el("button", { class: "icon", text: "Next ▶" });
  prevPage.disabled = state.page === 0;
  nextPage.disabled = !hasNext;
  prevPage.addEventListener("click", () => { state.page--; draw(host); });
  nextPage.addEventListener("click", () => { state.page++; draw(host); });
  const pager = el("div", { class: "pager" },
    el("span", { text: `Page ${state.page + 1}` }), prevPage, nextPage);

  /* ----- bulk bar ----- */
  const bulkCount = el("span", { class: "count" });
  const bulkbar = el("div", { class: "bulkbar", style: "display:none" }, bulkCount);

  const runBulk = async (payload, label) => {
    try {
      const result = await api.post("/transactions/bulk", { ids: [...selected], ...payload });
      toast(`${label}: ${result.deleted || result.updated} transaction(s)`);
      draw(host);
    } catch (error) { toast(error.message); }
  };

  const bulkCategory = select(
    [{ value: "", label: "Set category…" }, ...refdata.allCategoryOptions()], "");
  bulkCategory.addEventListener("change", () => {
    if (bulkCategory.value) runBulk({ set_category_id: Number(bulkCategory.value) }, "Recategorized");
  });
  const bulkAccount = select(
    [{ value: "", label: "Move to account…" },
     ...refdata.activeAccounts().map(a => ({ value: a.id, label: a.name }))], "");
  bulkAccount.addEventListener("change", () => {
    if (bulkAccount.value) runBulk({ set_account_id: Number(bulkAccount.value) }, "Moved");
  });

  const bulkPayee = el("button", { text: "Set payee" });
  bulkPayee.addEventListener("click", () => {
    const input = el("input", { type: "text", placeholder: "New payee" });
    openModal("Set payee on selected", field("Payee", input), {
      onSubmit: () => runBulk({ set_payee: input.value.trim() }, "Updated"),
    });
  });
  const bulkClear = el("button", { text: "Mark cleared" });
  bulkClear.addEventListener("click", () => runBulk({ set_cleared: true }, "Cleared"));
  const bulkUnclear = el("button", { text: "Mark uncleared" });
  bulkUnclear.addEventListener("click", () => runBulk({ set_cleared: false }, "Uncleared"));
  const bulkDelete = el("button", { class: "danger", text: "Delete" });
  bulkDelete.addEventListener("click", () =>
    confirmModal("Delete transactions",
      `Delete ${selected.size} transaction(s)? This cannot be undone.`,
      () => runBulk({ delete: true }, "Deleted")));

  bulkbar.append(bulkCategory, bulkAccount, bulkPayee, bulkClear, bulkUnclear, bulkDelete);

  host.replaceChildren(el("div", { class: "card" },
    el("h2", { text: "Transactions" }),
    filters,
    txns.length ? table : el("div", { class: "empty", text: "No transactions match." }),
    pager,
    bulkbar));
}

/* ---------- add/edit modal with split editor ---------- */

function editorModal(txn, onDone) {
  const isEdit = txn !== null;
  const accountSelect = select(
    refdata.activeAccounts().map(a => ({ value: a.id, label: a.name })),
    txn?.account_id ?? refdata.activeAccounts()[0]?.id);
  if (!refdata.activeAccounts().length) {
    toast("Create an account under Settings first");
    return;
  }
  const dateInput = el("input", { type: "date", value: txn?.date ?? today() });
  const payeeInput = el("input", { type: "text", value: txn?.payee ?? "", placeholder: "Payee" });
  const memoInput = el("input", { type: "text", value: txn?.memo ?? "", placeholder: "Memo (optional)" });
  const direction = select(
    [{ value: "-1", label: "Outflow (spending)" }, { value: "1", label: "Inflow (income/refund)" }],
    txn ? (txn.amount_cents < 0 ? "-1" : "1") : "-1");
  const amountInput = el("input", { class: "num", type: "text", inputmode: "decimal",
    value: txn ? centsToInput(Math.abs(txn.amount_cents)) : "", placeholder: "0.00" });
  const cleared = checkbox("Cleared", txn?.cleared ?? false);

  const categoryOptions = [
    { value: "", label: "— Uncategorized —" },
    ...refdata.allCategoryOptions(),
  ];
  const singleCategory = select(categoryOptions,
    txn && txn.splits.length === 1 ? (txn.splits[0].category_id ?? "") : "");

  /* split editor */
  const splitToggle = checkbox("Split across multiple categories",
    isEdit && txn.splits.length > 1);
  const splitRows = el("div", { class: "split-rows" });
  const splitSum = el("div", { class: "split-sum" });
  const addSplitButton = el("button", { class: "icon", type: "button", text: "+ Add split" });
  const splitSection = el("div", {}, splitRows, addSplitButton, splitSum);
  const singleSection = field("Category", singleCategory);

  function addSplitRow(categoryId = "", cents = 0, memo = "") {
    const categorySelect = select(categoryOptions, categoryId ?? "");
    const amount = el("input", { class: "num amt", type: "text", inputmode: "decimal",
      value: cents ? centsToInput(Math.abs(cents)) : "", placeholder: "0.00" });
    const memoField = el("input", { class: "memo", type: "text", value: memo, placeholder: "Memo" });
    const remove = el("button", { class: "icon danger", type: "button", text: "✕" });
    const row = el("div", { class: "split-row" }, categorySelect, amount, memoField, remove);
    remove.addEventListener("click", () => { row.remove(); updateSplitSum(); });
    amount.addEventListener("input", updateSplitSum);
    splitRows.append(row);
  }

  function splitData() {
    return [...splitRows.querySelectorAll(".split-row")].map(row => ({
      category_id: row.children[0].value ? Number(row.children[0].value) : null,
      cents: parseDollars(row.children[1].value || "0"),
      memo: row.children[2].value,
    }));
  }

  function updateSplitSum() {
    const total = parseDollars(amountInput.value || "0");
    const assigned = splitData().reduce((sum, s) => sum + (Number.isNaN(s.cents) ? 0 : s.cents), 0);
    const remaining = (Number.isNaN(total) ? 0 : total) - assigned;
    splitSum.textContent = remaining === 0
      ? "Splits balance ✓" : `Remaining to assign: ${fmt(remaining)}`;
    splitSum.classList.toggle("bad", remaining !== 0);
  }

  addSplitButton.addEventListener("click", () => { addSplitRow(); updateSplitSum(); });
  amountInput.addEventListener("input", () => { if (splitToggle.input.checked) updateSplitSum(); });

  const syncSplitVisibility = () => {
    const on = splitToggle.input.checked;
    splitSection.style.display = on ? "" : "none";
    singleSection.style.display = on ? "none" : "";
    if (on && !splitRows.children.length) {
      if (isEdit && txn.splits.length > 1) {
        txn.splits.forEach(s => addSplitRow(s.category_id, s.amount_cents, s.memo));
      } else {
        addSplitRow(); addSplitRow();
      }
      updateSplitSum();
    }
  };
  splitToggle.input.addEventListener("change", syncSplitVisibility);

  const body = el("div", {},
    el("div", { class: "form-grid" },
      field("Account", accountSelect), field("Date", dateInput),
      el("div", { class: "wide" }, field("Payee", payeeInput)),
      field("Direction", direction), field("Amount", amountInput),
      el("div", { class: "wide" }, field("Memo", memoInput))),
    cleared.node, splitToggle.node, singleSection, splitSection);
  syncSplitVisibility();

  openModal(isEdit ? "Edit transaction" : "Add transaction", body, {
    submitLabel: isEdit ? "Save changes" : "Add",
    onSubmit: async () => {
      const sign = Number(direction.value);
      const absCents = Math.abs(parseDollars(amountInput.value));
      if (Number.isNaN(absCents) || absCents === 0) { toast("Enter an amount"); return false; }
      const amountCents = sign * absCents;

      const payload = {
        account_id: Number(accountSelect.value),
        date: dateInput.value,
        payee: payeeInput.value.trim(),
        memo: memoInput.value.trim(),
        amount_cents: amountCents,
        cleared: cleared.input.checked,
      };
      if (splitToggle.input.checked) {
        const splits = splitData().filter(s => !Number.isNaN(s.cents) && s.cents !== 0);
        if (!splits.length) { toast("Add at least one split"); return false; }
        payload.splits = splits.map(s => ({
          category_id: s.category_id, amount_cents: sign * Math.abs(s.cents), memo: s.memo,
        }));
        const sum = payload.splits.reduce((total, s) => total + s.amount_cents, 0);
        if (sum !== amountCents) {
          toast(`Splits total ${fmt(sum)} but amount is ${fmt(amountCents)}`);
          return false;
        }
      } else {
        // Always send an explicit single split so edits collapse former
        // multi-splits and "Uncategorized" (null) round-trips cleanly.
        payload.splits = [{
          category_id: singleCategory.value ? Number(singleCategory.value) : null,
          amount_cents: amountCents,
          memo: "",
        }];
      }

      if (isEdit) await api.patch(`/transactions/${txn.id}`, payload);
      else await api.post("/transactions", payload);
      toast(isEdit ? "Transaction updated" : "Transaction added");
      onDone();
    },
  });
}
