"use strict";

import { api } from "../api.js";
import { el, toast } from "../dom.js";
import { fmt, parseDollars, centsToInput, currentMonth, monthAdd, monthLabel } from "../format.js";

let month = currentMonth();

export async function render(host) {
  const budget = await api.get(`/budget/${month}`);
  const spendRows = budget.categories.filter(c => !c.is_income);
  const incomeRows = budget.categories.filter(c => c.is_income);

  /* month navigation + TBB summary */
  const prev = el("button", { class: "icon", text: "◀", "aria-label": "Previous month" });
  const next = el("button", { class: "icon", text: "▶", "aria-label": "Next month" });
  prev.addEventListener("click", () => { month = monthAdd(month, -1); render(host); });
  next.addEventListener("click", () => { month = monthAdd(month, 1); render(host); });

  const copyLast = el("button", { text: "Copy last month’s assignments" });
  copyLast.addEventListener("click", async () => {
    copyLast.disabled = true;
    try {
      const lastBudget = await api.get(`/budget/${monthAdd(month, -1)}`);
      const toCopy = lastBudget.categories.filter(c => !c.is_income && c.allocated_cents !== 0);
      if (!toCopy.length) { toast("Nothing assigned last month"); copyLast.disabled = false; return; }
      for (const row of toCopy) {
        await api.put("/budget/allocations", {
          month, category_id: row.category_id, amount_cents: row.allocated_cents,
        });
      }
      toast(`Copied ${toCopy.length} assignment(s) from last month`);
      render(host);
    } catch (error) { toast("Copy failed: " + error.message); copyLast.disabled = false; }
  });

  const tbb = budget.to_be_budgeted_cents;
  const header = el("div", { class: "card" },
    el("div", { class: "month-nav" },
      prev, el("h2", { text: monthLabel(month) }), next,
      el("span", { class: "spacer" }), copyLast),
    el("div", { class: "row kpis", style: "margin:12px 0 4px" },
      el("div", { class: "tile" },
        el("div", { class: "label", text: "To be budgeted" }),
        el("div", { class: "value" + (tbb < 0 ? " negative" : ""), text: fmt(tbb) }),
        el("div", { class: "hint", text: tbb === 0 ? "every dollar has a job"
          : tbb > 0 ? "assign it below to reach zero" : "over-assigned — reduce an assignment" })),
      el("div", { class: "tile" },
        el("div", { class: "label", text: "Income this month" }),
        el("div", { class: "value", text: fmt(budget.income_cents) })),
      el("div", { class: "tile" },
        el("div", { class: "label", text: "Assigned this month" }),
        el("div", { class: "value", text: fmt(budget.allocated_cents) })),
      el("div", { class: "tile" },
        el("div", { class: "label", text: "Spending this month" }),
        el("div", { class: "value", text: fmt(budget.activity_cents) }))));

  /* editable allocation table */
  const body = el("tbody");
  let currentGroup = null;
  for (const row of spendRows) {
    if (row.group !== currentGroup) {
      currentGroup = row.group;
      body.append(el("tr", { class: "group-row no-hover" },
        el("td", { colspan: "4", text: currentGroup })));
    }
    const input = el("input", {
      class: "alloc", type: "text", value: centsToInput(row.allocated_cents),
      "aria-label": `Assigned to ${row.name}`,
    });
    const save = async () => {
      const cents = parseDollars(input.value);
      if (Number.isNaN(cents)) { toast("Enter a number"); input.focus(); return; }
      if (cents === row.allocated_cents) return;
      try {
        await api.put("/budget/allocations", { month, category_id: row.category_id, amount_cents: cents });
        toast(`Assigned ${fmt(cents)} to ${row.name}`);
        render(host);
      } catch (error) { toast("Save failed: " + error.message); }
    };
    input.addEventListener("keydown", (event) => { if (event.key === "Enter") save(); });
    input.addEventListener("blur", save);

    const availableCell = el("td", { class: "num" });
    if (row.available_cents < 0) {
      availableCell.append(el("span", { class: "badge-neg", text: fmt(row.available_cents) }));
    } else {
      availableCell.textContent = fmt(row.available_cents);
    }
    body.append(el("tr", { class: "no-hover" },
      el("td", { text: row.name }),
      el("td", { class: "num" }, input),
      el("td", { class: "num" + (row.activity_cents < 0 ? " neg" : ""), text: fmt(row.activity_cents) }),
      availableCell));
  }

  const budgetCard = el("div", { class: "card" },
    el("h2", {}, "Envelopes ", el("span", { class: "note", text: "(edit “Assigned”; Enter or click away to save)" })),
    spendRows.length
      ? el("div", { class: "table-scroll" }, el("table", {},
          el("thead", {}, el("tr", {},
            el("th", { text: "Category" }), el("th", { class: "num", text: "Assigned" }),
            el("th", { class: "num", text: "Activity" }), el("th", { class: "num", text: "Available" }))),
          body))
      : el("div", { class: "empty", text: "No categories yet — create them under Settings." }));

  /* income summary */
  const incomeCard = el("div", { class: "card" },
    el("h2", { text: "Income" }),
    incomeRows.length
      ? el("table", {},
          el("thead", {}, el("tr", {},
            el("th", { text: "Category" }), el("th", { class: "num", text: "Received this month" }))),
          el("tbody", {}, ...incomeRows.map(row => el("tr", { class: "no-hover" },
            el("td", { text: row.name }),
            el("td", { class: "num", text: fmt(row.activity_cents) })))))
      : el("div", { class: "empty", text: "No income categories yet — create one under Settings." }));

  host.replaceChildren(header,
    el("div", { class: "row two-col" }, budgetCard, incomeCard));
}
