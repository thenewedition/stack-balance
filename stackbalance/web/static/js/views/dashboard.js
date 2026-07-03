"use strict";

import { api } from "../api.js";
import { el, toast } from "../dom.js";
import { fmt, currentMonth, monthLabel } from "../format.js";
import { cashFlowChart, spendingChart, meter } from "../charts.js";
import * as refdata from "../refdata.js";

function tile(label, value, hint, options = {}) {
  const long = options.hero && value.length > 9 ? " long" : "";
  return el("div", { class: "card tile" + (options.hero ? " hero" : "") },
    el("div", { class: "label", text: label }),
    el("div", { class: "value" + long + (options.negative ? " negative" : ""), text: value }),
    hint ? el("div", { class: "hint", text: hint }) : null);
}

export async function render(host) {
  const month = currentMonth();
  await refdata.load(true);
  const [budget, burn, cashFlow, spending, funds, txns] = await Promise.all([
    api.get(`/budget/${month}`),
    api.get("/reports/burn-rate?window_days=30"),
    api.get("/reports/cash-flow?months=12"),
    api.get(`/reports/spending/${month}`),
    api.get("/sinking-funds"),
    api.get("/transactions?limit=10"),
  ]);

  /* KPI row */
  const tbb = budget.to_be_budgeted_cents;
  const runway = burn.runway_days === null ? "∞"
    : burn.runway_days > 365 ? "1 yr+" : burn.runway_days + " days";
  const kpis = el("div", { class: "row kpis" },
    tile("To be budgeted", fmt(tbb),
      tbb === 0 ? "every dollar has a job" : tbb > 0 ? "assign it on the Budget page" : "over-assigned — pull some back",
      { hero: true, negative: tbb < 0 }),
    tile("Liquid balance", fmt(burn.liquid_balance_cents), "on-budget accounts"),
    tile("Daily burn", fmt(burn.daily_burn_cents), "avg spend, last 30 days"),
    tile("Runway", runway,
      burn.runway_date ? "funds last until " + burn.runway_date : "no burn detected"));

  /* Cash flow card */
  const cashFlowCard = el("div", { class: "card" },
    el("h2", { text: "Cash flow — last 12 months" }),
    el("div", { class: "legend" },
      el("span", { class: "key" }, el("span", { class: "swatch", style: "background:var(--income)" }), "Income"),
      el("span", { class: "key" }, el("span", { class: "swatch", style: "background:var(--expense)" }), "Spending")),
    cashFlowChart(cashFlow.months),
    el("details", {}, el("summary", { text: "Data table" }),
      el("div", { class: "table-scroll" }, el("table", {},
        el("thead", {}, el("tr", {},
          el("th", { text: "Month" }), el("th", { class: "num", text: "Income" }),
          el("th", { class: "num", text: "Spending" }), el("th", { class: "num", text: "Net" }))),
        el("tbody", {}, ...cashFlow.months.map(m => el("tr", { class: "no-hover" },
          el("td", { text: m.month }),
          el("td", { class: "num", text: fmt(m.income_cents) }),
          el("td", { class: "num", text: fmt(m.expense_cents) }),
          el("td", { class: "num" + (m.net_cents < 0 ? " neg" : ""), text: fmt(m.net_cents) }))))))));

  /* Spending card */
  const spendingCard = el("div", { class: "card" },
    el("h2", { text: `Spending by category — ${monthLabel(month)}` }),
    spending.length ? spendingChart(spending)
      : el("div", { class: "empty", text: "No spending recorded this month yet." }));

  /* Sinking funds card */
  const fundsCard = el("div", { class: "card" },
    el("h2", { text: "Sinking funds" }),
    funds.length ? el("div", {}, ...funds.map(fund => {
      const pace = fund.suggested_monthly_cents !== null && fund.remaining_cents > 0
        ? `${fmt(fund.suggested_monthly_cents)}/mo to hit ${fund.target_date}` : (fund.target_date || "");
      return el("div", { class: "fund" },
        el("div", { class: "top" },
          el("span", { text: fund.name }),
          el("span", { text: `${fmt(fund.saved_cents)} / ${fmt(fund.target_cents)}` })),
        meter(fund.percent_complete),
        el("div", { class: "bottom" },
          el("span", { text: fund.percent_complete + "%" }),
          el("span", { text: pace })));
    })) : el("div", { class: "empty", text: "No sinking funds yet — add one under Settings." }));

  /* Quick actions + recent transactions */
  const runRecurring = el("button", { text: "Run recurring" });
  runRecurring.addEventListener("click", async () => {
    try {
      const result = await api.post("/recurring/run", {});
      toast(result.posted ? `Posted ${result.posted} recurring transaction(s)` : "Nothing due");
      if (result.posted) render(hostRef);
    } catch (error) { toast("Failed: " + error.message); }
  });
  const backupNow = el("button", { text: "Backup now" });
  backupNow.addEventListener("click", async () => {
    try {
      const backup = await api.post("/backups", {});
      toast(`Backup saved: ${backup.filename}`);
      window.open(`/api/backups/${encodeURIComponent(backup.filename)}`, "_blank");
    } catch (error) { toast("Backup failed: " + error.message); }
  });

  const txnCard = el("div", { class: "card" },
    el("h2", {}, "Recent transactions ",
      el("a", { href: "#/transactions", class: "note", text: "see all →" })),
    txns.length ? el("div", { class: "table-scroll" }, el("table", {},
      el("thead", {}, el("tr", {},
        el("th", { text: "Date" }), el("th", { text: "Account" }), el("th", { text: "Payee" }),
        el("th", { text: "Category" }), el("th", { class: "num", text: "Amount" }))),
      el("tbody", {}, ...txns.map(txn => el("tr", { class: "no-hover" },
        el("td", { text: txn.date }),
        el("td", { text: refdata.accountName(txn.account_id) }),
        el("td", { text: txn.payee || "—" }),
        el("td", { text: txn.splits.length > 1
          ? `${txn.splits.length}-way split: ` + txn.splits.map(s => refdata.categoryName(s.category_id)).join(", ")
          : refdata.categoryName(txn.splits[0]?.category_id) }),
        el("td", { class: "num" + (txn.amount_cents < 0 ? " neg" : ""), text: fmt(txn.amount_cents) }))))))
    : el("div", { class: "empty", text: "No transactions yet — add one on the Transactions page or import a file." }));

  const hostRef = host;
  host.replaceChildren(
    el("div", { class: "month-nav" },
      el("h2", { text: monthLabel(month) }),
      el("span", { class: "spacer" }), runRecurring, backupNow),
    kpis,
    el("div", { class: "row two-col" }, cashFlowCard, spendingCard),
    el("div", { class: "row two-col" }, txnCard, fundsCard));
}
