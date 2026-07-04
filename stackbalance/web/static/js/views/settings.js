"use strict";

import { api } from "../api.js";
import { el, toast, openModal, confirmModal, field, checkbox, select } from "../dom.js";
import { fmt, parseDollars, centsToInput, today } from "../format.js";
import * as refdata from "../refdata.js";

const ACCOUNT_TYPES = ["checking", "savings", "cash", "credit", "investment", "other"]
  .map(t => ({ value: t, label: t[0].toUpperCase() + t.slice(1) }));
const FREQUENCIES = ["daily", "weekly", "biweekly", "monthly", "yearly"]
  .map(f => ({ value: f, label: f[0].toUpperCase() + f.slice(1) }));

export async function render(host) {
  await refdata.load(true);
  const refresh = () => render(host);
  const [rules, funds, backups, catRules] = await Promise.all([
    api.get("/recurring?include_inactive=true"),
    api.get("/sinking-funds"),
    api.get("/backups"),
    api.get("/categorization-rules"),
  ]);
  host.replaceChildren(
    accountsCard(refresh),
    categoriesCard(refresh),
    autocatCard(catRules, refresh),
    recurringCard(rules, refresh),
    fundsCard(funds, refresh),
    backupsCard(backups, refresh));
}

/* ---------- auto-categorization rules ---------- */

function autocatCard(rules, refresh) {
  const patternInput = el("input", { type: "text", placeholder: "Payee contains…" });
  const matchSelect = select([
    { value: "contains", label: "Contains" },
    { value: "exact", label: "Exact match" },
  ]);
  const categoryOptions = refdata.allCategoryOptions();
  const categorySelect = select(categoryOptions);
  const addButton = el("button", { class: "primary", text: "Add rule" });
  addButton.addEventListener("click", async () => {
    if (!patternInput.value.trim()) { toast("Enter a payee pattern"); return; }
    if (!categoryOptions.length) { toast("Create a category first"); return; }
    try {
      await api.post("/categorization-rules", {
        pattern: patternInput.value.trim(),
        match_type: matchSelect.value,
        category_id: Number(categorySelect.value),
      });
      toast("Rule saved");
      refresh();
    } catch (error) { toast(error.message); }
  });

  const applyButton = el("button", { text: "Apply to existing uncategorized" });
  applyButton.addEventListener("click", async () => {
    const result = await api.post("/categorization-rules/apply", {});
    toast(result.matched
      ? `Categorized ${result.matched} existing transaction(s)`
      : "No uncategorized transactions matched");
  });

  const rows = rules.map(rule => {
    const deleteButton = el("button", { class: "icon danger", text: "Delete" });
    deleteButton.addEventListener("click", async () => {
      await api.del(`/categorization-rules/${rule.id}`);
      refresh();
    });
    return el("tr", { class: "no-hover" },
      el("td", { text: rule.pattern }),
      el("td", { class: "muted", text: rule.match_type }),
      el("td", { text: refdata.categoryName(rule.category_id) }),
      el("td", { class: "right" }, deleteButton));
  });

  return el("div", { class: "card" },
    el("h2", { text: "Auto-categorization rules" }),
    el("p", { class: "muted", style: "font-size:12px" },
      "Imported transactions whose file has no category get the matching rule's category. Exact matches beat “contains”; longer patterns beat shorter ones. You can also save a rule from the transaction editor."),
    rules.length
      ? el("div", { class: "table-scroll" }, el("table", {},
          el("thead", {}, el("tr", {},
            el("th", { text: "Payee pattern" }), el("th", { text: "Match" }),
            el("th", { text: "Category" }), el("th"))),
          el("tbody", {}, ...rows)))
      : el("div", { class: "empty", text: "No rules yet." }),
    el("div", { class: "inline-form" },
      patternInput, matchSelect, categorySelect, addButton, applyButton));
}

/* ---------- accounts ---------- */

function accountModal(account, refresh) {
  const isEdit = account !== null;
  const nameInput = el("input", { type: "text", value: account?.name ?? "" });
  const typeSelect = select(ACCOUNT_TYPES, account?.type ?? "checking");
  const openingInput = el("input", { class: "num", type: "text",
    value: account ? centsToInput(account.opening_balance_cents) : "0.00" });
  const onBudget = checkbox("On budget (counts toward envelopes & reports)",
    account?.on_budget ?? true);
  const active = checkbox("Active", account?.is_active ?? true);

  openModal(isEdit ? "Edit account" : "Add account", el("div", {},
    field("Name", nameInput),
    field("Type", typeSelect),
    field("Opening balance ($)", openingInput),
    onBudget.node, isEdit ? active.node : null), {
    submitLabel: isEdit ? "Save" : "Add",
    onSubmit: async () => {
      const opening = parseDollars(openingInput.value);
      if (!nameInput.value.trim()) { toast("Name is required"); return false; }
      if (Number.isNaN(opening)) { toast("Opening balance must be a number"); return false; }
      const payload = {
        name: nameInput.value.trim(), type: typeSelect.value,
        opening_balance_cents: opening, on_budget: onBudget.input.checked,
      };
      if (isEdit) {
        payload.is_active = active.input.checked;
        await api.patch(`/accounts/${account.id}`, payload);
      } else {
        await api.post("/accounts", payload);
      }
      refdata.invalidate();
      refresh();
    },
  });
}

function accountsCard(refresh) {
  const addButton = el("button", { class: "primary", text: "Add account" });
  addButton.addEventListener("click", () => accountModal(null, refresh));

  const rows = refdata.data.accounts.map(account => {
    const editButton = el("button", { class: "icon", text: "Edit" });
    editButton.addEventListener("click", () => accountModal(account, refresh));
    const deleteButton = el("button", { class: "icon danger", text: "Delete" });
    deleteButton.addEventListener("click", () =>
      confirmModal("Delete account", `Delete “${account.name}”? Only possible if it has no transactions.`,
        async () => {
          await api.del(`/accounts/${account.id}`);
          refdata.invalidate();
          toast("Account deleted");
          refresh();
        }));
    return el("tr", { class: "no-hover" },
      el("td", { text: account.name }),
      el("td", { class: "muted", text: account.type }),
      el("td", { class: "num", text: fmt(account.balance_cents) }),
      el("td", { class: "num", text: fmt(account.cleared_balance_cents) }),
      el("td", { text: account.on_budget ? "✓" : "" }),
      el("td", { class: "muted", text: account.last_reconciled_at
        ? account.last_reconciled_at.slice(0, 10) : "never" }),
      el("td", { text: account.is_active ? "" : "inactive" }),
      el("td", { class: "right" }, editButton, " ", deleteButton));
  });

  return el("div", { class: "card" },
    el("h2", {}, "Accounts ", el("span", { class: "spacer" })),
    refdata.data.accounts.length
      ? el("div", { class: "table-scroll" }, el("table", {},
          el("thead", {}, el("tr", {},
            el("th", { text: "Name" }), el("th", { text: "Type" }),
            el("th", { class: "num", text: "Balance" }), el("th", { class: "num", text: "Cleared" }),
            el("th", { text: "On budget" }), el("th", { text: "Last reconciled" }),
            el("th"), el("th"))),
          el("tbody", {}, ...rows)))
      : el("div", { class: "empty", text: "No accounts yet." }),
    el("div", { class: "inline-form" }, addButton));
}

/* ---------- categories ---------- */

function categoriesCard(refresh) {
  const groupNameInput = el("input", { type: "text", placeholder: "New group name" });
  const addGroupButton = el("button", { text: "Add group" });
  addGroupButton.addEventListener("click", async () => {
    if (!groupNameInput.value.trim()) return;
    try {
      await api.post("/category-groups", { name: groupNameInput.value.trim() });
      refdata.invalidate();
      refresh();
    } catch (error) { toast(error.message); }
  });

  const sections = refdata.data.groups.map(group => {
    const categories = refdata.data.categories.filter(c => c.group_id === group.id);
    const categoryRows = categories.map(category => {
      const renameButton = el("button", { class: "icon", text: "Rename" });
      renameButton.addEventListener("click", () => {
        const input = el("input", { type: "text", value: category.name });
        openModal("Rename category", field("Name", input), {
          onSubmit: async () => {
            await api.patch(`/categories/${category.id}`, { name: input.value.trim() });
            refdata.invalidate();
            refresh();
          },
        });
      });
      const archiveButton = el("button", { class: "icon",
        text: category.is_archived ? "Unarchive" : "Archive" });
      archiveButton.addEventListener("click", async () => {
        await api.patch(`/categories/${category.id}`, { is_archived: !category.is_archived });
        refdata.invalidate();
        refresh();
      });
      const deleteButton = el("button", { class: "icon danger", text: "Delete" });
      deleteButton.addEventListener("click", () =>
        confirmModal("Delete category",
          `Delete “${category.name}”? Only possible if it has no transaction activity.`,
          async () => {
            await api.del(`/categories/${category.id}`);
            refdata.invalidate();
            toast("Category deleted");
            refresh();
          }));
      return el("tr", { class: "no-hover" },
        el("td", { text: category.name }),
        el("td", { class: "muted", text: (category.is_income ? "income" : "") +
          (category.is_archived ? " · archived" : "") }),
        el("td", { class: "right" }, renameButton, " ", archiveButton, " ", deleteButton));
    });

    const newCategoryInput = el("input", { type: "text", placeholder: "New category" });
    const incomeCheck = checkbox("Income", false);
    const addCategoryButton = el("button", { class: "icon", text: "Add" });
    addCategoryButton.addEventListener("click", async () => {
      if (!newCategoryInput.value.trim()) return;
      try {
        await api.post("/categories", {
          group_id: group.id, name: newCategoryInput.value.trim(),
          is_income: incomeCheck.input.checked,
        });
        refdata.invalidate();
        refresh();
      } catch (error) { toast(error.message); }
    });
    const deleteGroupButton = el("button", { class: "icon danger", text: "Delete group" });
    deleteGroupButton.addEventListener("click", () =>
      confirmModal("Delete group", `Delete group “${group.name}”? It must be empty.`,
        async () => {
          await api.del(`/category-groups/${group.id}`);
          refdata.invalidate();
          toast("Group deleted");
          refresh();
        }));

    return el("div", { style: "margin-bottom:16px" },
      el("div", { class: "section-title", style: "margin:14px 0 6px; font-size:13px" },
        group.name, " ", categories.length === 0 ? deleteGroupButton : null),
      categoryRows.length
        ? el("table", {}, el("tbody", {}, ...categoryRows))
        : el("div", { class: "empty", text: "No categories in this group." }),
      el("div", { class: "inline-form" },
        newCategoryInput, incomeCheck.node, addCategoryButton));
  });

  return el("div", { class: "card" },
    el("h2", { text: "Category groups & categories" }),
    ...(sections.length ? sections
      : [el("div", { class: "empty", text: "No category groups yet — start with “Income”, “Bills”, “Everyday”." })]),
    el("div", { class: "inline-form" }, groupNameInput, addGroupButton));
}

/* ---------- recurring rules ---------- */

function ruleModal(rule, refresh) {
  const isEdit = rule !== null;
  const nameInput = el("input", { type: "text", value: rule?.name ?? "" });
  const accountSelect = select(
    refdata.activeAccounts().map(a => ({ value: a.id, label: a.name })),
    rule?.account_id ?? refdata.activeAccounts()[0]?.id);
  const payeeInput = el("input", { type: "text", value: rule?.payee ?? "" });
  const direction = select(
    [{ value: "-1", label: "Outflow" }, { value: "1", label: "Inflow" }],
    rule ? (rule.amount_cents < 0 ? "-1" : "1") : "-1");
  const amountInput = el("input", { class: "num", type: "text",
    value: rule ? centsToInput(Math.abs(rule.amount_cents)) : "", placeholder: "0.00" });
  const categorySelect = select(
    [{ value: "", label: "— Uncategorized —" }, ...refdata.allCategoryOptions()],
    rule?.category_id ?? "");
  const frequencySelect = select(FREQUENCIES, rule?.frequency ?? "monthly");
  const intervalInput = el("input", { class: "num", type: "number", min: "1",
    value: String(rule?.interval ?? 1) });
  const nextDateInput = el("input", { type: "date", value: rule?.next_date ?? today() });
  const endDateInput = el("input", { type: "date", value: rule?.end_date ?? "" });
  const activeCheck = checkbox("Active", rule?.is_active ?? true);

  openModal(isEdit ? "Edit recurring rule" : "Add recurring rule", el("div", {},
    el("div", { class: "form-grid" },
      el("div", { class: "wide" }, field("Name", nameInput)),
      field("Account", accountSelect), field("Payee", payeeInput),
      field("Direction", direction), field("Amount ($)", amountInput),
      el("div", { class: "wide" }, field("Category", categorySelect)),
      field("Frequency", frequencySelect), field("Every N periods", intervalInput),
      field("Next date", nextDateInput), field("End date (optional)", endDateInput)),
    isEdit ? activeCheck.node : null), {
    submitLabel: isEdit ? "Save" : "Add",
    onSubmit: async () => {
      const absCents = Math.abs(parseDollars(amountInput.value));
      if (!nameInput.value.trim()) { toast("Name is required"); return false; }
      if (Number.isNaN(absCents) || absCents === 0) { toast("Enter an amount"); return false; }
      const payload = {
        name: nameInput.value.trim(),
        account_id: Number(accountSelect.value),
        payee: payeeInput.value.trim(),
        amount_cents: Number(direction.value) * absCents,
        category_id: categorySelect.value ? Number(categorySelect.value) : null,
        frequency: frequencySelect.value,
        interval: Math.max(1, Number(intervalInput.value) || 1),
        next_date: nextDateInput.value,
        end_date: endDateInput.value || null,
      };
      if (isEdit) {
        payload.is_active = activeCheck.input.checked;
        await api.patch(`/recurring/${rule.id}`, payload);
      } else {
        await api.post("/recurring", payload);
      }
      refresh();
    },
  });
}

function recurringCard(rules, refresh) {
  const addButton = el("button", { class: "primary", text: "Add rule" });
  addButton.addEventListener("click", () => {
    if (!refdata.activeAccounts().length) { toast("Create an account first"); return; }
    ruleModal(null, refresh);
  });
  const runButton = el("button", { text: "Run engine now" });
  runButton.addEventListener("click", async () => {
    const result = await api.post("/recurring/run", {});
    toast(result.posted ? `Posted ${result.posted} transaction(s)` : "Nothing due");
    if (result.posted) refresh();
  });

  const rows = rules.map(rule => {
    const editButton = el("button", { class: "icon", text: "Edit" });
    editButton.addEventListener("click", () => ruleModal(rule, refresh));
    const deleteButton = el("button", { class: "icon danger", text: "Delete" });
    deleteButton.addEventListener("click", () =>
      confirmModal("Delete rule", `Delete “${rule.name}”? Already-posted transactions stay.`,
        async () => {
          await api.del(`/recurring/${rule.id}`);
          toast("Rule deleted");
          refresh();
        }));
    return el("tr", { class: "no-hover" },
      el("td", { text: rule.name }),
      el("td", { text: refdata.accountName(rule.account_id) }),
      el("td", { class: "num" + (rule.amount_cents < 0 ? " neg" : ""), text: fmt(rule.amount_cents) }),
      el("td", { class: "muted", text: rule.interval > 1
        ? `every ${rule.interval} ${rule.frequency.replace("ly", "")}s` : rule.frequency }),
      el("td", { text: rule.next_date }),
      el("td", { text: rule.is_active ? "" : "paused" }),
      el("td", { class: "right" }, editButton, " ", deleteButton));
  });

  return el("div", { class: "card" },
    el("h2", { text: "Recurring transactions" }),
    rules.length
      ? el("div", { class: "table-scroll" }, el("table", {},
          el("thead", {}, el("tr", {},
            el("th", { text: "Name" }), el("th", { text: "Account" }),
            el("th", { class: "num", text: "Amount" }), el("th", { text: "Schedule" }),
            el("th", { text: "Next date" }), el("th"), el("th"))),
          el("tbody", {}, ...rows)))
      : el("div", { class: "empty", text: "No recurring rules yet." }),
    el("div", { class: "inline-form" }, addButton, runButton));
}

/* ---------- sinking funds ---------- */

function fundModal(fund, refresh) {
  const isEdit = fund !== null;
  const spendingOptions = refdata.spendingCategories()
    .map(c => ({ value: c.id, label: `${refdata.groupName(c.group_id)}: ${c.name}` }));
  if (!spendingOptions.length) { toast("Create a spending category first"); return; }
  const nameInput = el("input", { type: "text", value: fund?.name ?? "" });
  const categorySelect = select(spendingOptions, fund?.category_id ?? spendingOptions[0].value);
  const targetInput = el("input", { class: "num", type: "text",
    value: fund ? centsToInput(fund.target_cents) : "", placeholder: "0.00" });
  const targetDateInput = el("input", { type: "date", value: fund?.target_date ?? "" });
  const notesInput = el("input", { type: "text", value: fund?.notes ?? "" });

  openModal(isEdit ? "Edit sinking fund" : "Add sinking fund", el("div", {},
    field("Name", nameInput),
    field("Linked category (its envelope balance is the fund)", categorySelect),
    field("Target amount ($)", targetInput),
    field("Target date (optional)", targetDateInput),
    field("Notes", notesInput)), {
    submitLabel: isEdit ? "Save" : "Add",
    onSubmit: async () => {
      const target = parseDollars(targetInput.value);
      if (!nameInput.value.trim()) { toast("Name is required"); return false; }
      if (Number.isNaN(target) || target <= 0) { toast("Target must be positive"); return false; }
      const payload = {
        name: nameInput.value.trim(),
        category_id: Number(categorySelect.value),
        target_cents: target,
        target_date: targetDateInput.value || null,
        notes: notesInput.value.trim(),
      };
      if (isEdit) await api.patch(`/sinking-funds/${fund.id}`, payload);
      else await api.post("/sinking-funds", payload);
      refresh();
    },
  });
}

function fundsCard(funds, refresh) {
  const addButton = el("button", { class: "primary", text: "Add sinking fund" });
  addButton.addEventListener("click", () => fundModal(null, refresh));

  const rows = funds.map(fund => {
    const editButton = el("button", { class: "icon", text: "Edit" });
    editButton.addEventListener("click", () => fundModal(fund, refresh));
    const deleteButton = el("button", { class: "icon danger", text: "Delete" });
    deleteButton.addEventListener("click", () =>
      confirmModal("Delete fund", `Delete “${fund.name}”? The category and its money stay.`,
        async () => {
          await api.del(`/sinking-funds/${fund.id}`);
          toast("Fund deleted");
          refresh();
        }));
    return el("tr", { class: "no-hover" },
      el("td", { text: fund.name }),
      el("td", { text: refdata.categoryName(fund.category_id) }),
      el("td", { class: "num", text: `${fmt(fund.saved_cents)} / ${fmt(fund.target_cents)}` }),
      el("td", { text: fund.percent_complete + "%" }),
      el("td", { text: fund.target_date ?? "—" }),
      el("td", { text: fund.on_track === null ? "" : fund.on_track ? "on track" : "behind" }),
      el("td", { class: "right" }, editButton, " ", deleteButton));
  });

  return el("div", { class: "card" },
    el("h2", { text: "Sinking funds" }),
    funds.length
      ? el("div", { class: "table-scroll" }, el("table", {},
          el("thead", {}, el("tr", {},
            el("th", { text: "Name" }), el("th", { text: "Category" }),
            el("th", { class: "num", text: "Progress" }), el("th", { text: "%" }),
            el("th", { text: "Target date" }), el("th"), el("th"))),
          el("tbody", {}, ...rows)))
      : el("div", { class: "empty", text: "No sinking funds yet." }),
    el("div", { class: "inline-form" }, addButton));
}

/* ---------- backups ---------- */

function backupsCard(backups, refresh) {
  const createButton = el("button", { class: "primary", text: "Create backup" });
  createButton.addEventListener("click", async () => {
    const backup = await api.post("/backups", {});
    toast(`Backup saved: ${backup.filename}`);
    refresh();
  });

  const restoreInput = el("input", { type: "file", accept: ".zip", style: "display:none" });
  const restoreButton = el("button", { text: "Restore from file…" });
  restoreButton.addEventListener("click", () => restoreInput.click());
  restoreInput.addEventListener("change", () => {
    const file = restoreInput.files[0];
    if (!file) return;
    confirmModal("Restore backup",
      `Restore from “${file.name}”? This REPLACES all current data with the backup's contents.`,
      async () => {
        const result = await api.upload("/backups/restore", {}, file);
        toast("Restored: " + Object.entries(result.counts)
          .map(([table, count]) => `${count} ${table}`).join(", "));
        refdata.invalidate();
        refresh();
      }, "Replace everything");
    restoreInput.value = "";
  });

  const rows = backups.map(backup => {
    const deleteButton = el("button", { class: "icon danger", text: "Delete" });
    deleteButton.addEventListener("click", () =>
      confirmModal("Delete backup", `Delete ${backup.filename}?`, async () => {
        await api.del(`/backups/${encodeURIComponent(backup.filename)}`);
        refresh();
      }));
    return el("tr", { class: "no-hover" },
      el("td", { text: backup.filename }),
      el("td", { class: "muted", text: new Date(backup.created_at).toLocaleString() }),
      el("td", { class: "num", text: (backup.size_bytes / 1024).toFixed(1) + " KB" }),
      el("td", { class: "right" },
        el("a", { class: "btn", style: "padding:3px 8px;font-size:12px",
          href: `/api/backups/${encodeURIComponent(backup.filename)}`, text: "Download" }),
        " ", deleteButton));
  });

  return el("div", { class: "card" },
    el("h2", { text: "Backups" }),
    el("p", { class: "muted", style: "font-size:12px" },
      "A backup is a portable zip (JSON export + SQL dump). Keep copies somewhere safe — this is a local-first app, so there is no cloud copy."),
    backups.length
      ? el("div", { class: "table-scroll" }, el("table", {},
          el("thead", {}, el("tr", {},
            el("th", { text: "File" }), el("th", { text: "Created" }),
            el("th", { class: "num", text: "Size" }), el("th"))),
          el("tbody", {}, ...rows)))
      : el("div", { class: "empty", text: "No backups yet." }),
    el("div", { class: "inline-form" }, createButton, restoreButton));
}
