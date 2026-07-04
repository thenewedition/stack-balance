"use strict";

import { api } from "../api.js";
import { el, select } from "../dom.js";
import { fmt } from "../format.js";
import { netWorthChart, trendChart } from "../charts.js";
import * as refdata from "../refdata.js";

const state = { trendCategoryId: null, payeeMonths: "1" };

export async function render(host) {
  await refdata.load(true);

  /* ----- net worth ----- */
  const netWorth = await api.get("/reports/net-worth?months=12");
  const latest = netWorth.months[netWorth.months.length - 1];
  const netWorthCard = el("div", { class: "card" },
    el("h2", { text: "Net worth — last 12 months" }),
    el("div", { class: "summary-chips", style: "margin-bottom:8px" },
      el("span", {}, "Assets: ", el("b", { text: fmt(latest.assets_cents) })),
      el("span", {}, "Debts: ", el("b", { text: fmt(latest.debts_cents) })),
      el("span", {}, "Net worth: ", el("b", { text: fmt(latest.net_cents) }))),
    netWorthChart(netWorth.months),
    el("details", {}, el("summary", { text: "Data table" }),
      el("div", { class: "table-scroll" }, el("table", {},
        el("thead", {}, el("tr", {},
          el("th", { text: "Month" }), el("th", { class: "num", text: "Assets" }),
          el("th", { class: "num", text: "Debts" }), el("th", { class: "num", text: "Net worth" }))),
        el("tbody", {}, ...netWorth.months.map(m => el("tr", { class: "no-hover" },
          el("td", { text: m.month }),
          el("td", { class: "num", text: fmt(m.assets_cents) }),
          el("td", { class: "num" + (m.debts_cents < 0 ? " neg" : ""), text: fmt(m.debts_cents) }),
          el("td", { class: "num", text: fmt(m.net_cents) }))))))));

  /* ----- category trend ----- */
  const options = refdata.allCategoryOptions()
    .filter(o => !refdata.data.categories.find(c => c.id === o.value)?.is_income);
  const trendHost = el("div");
  const trendCard = el("div", { class: "card" }, el("h2", { text: "Category trend — last 12 months" }));
  if (!options.length) {
    trendCard.append(el("div", { class: "empty", text: "No spending categories yet." }));
  } else {
    if (!options.some(o => o.value === state.trendCategoryId)) {
      state.trendCategoryId = options[0].value;
    }
    const picker = select(options, state.trendCategoryId);
    picker.addEventListener("change", () => {
      state.trendCategoryId = Number(picker.value);
      drawTrend();
    });
    trendCard.append(el("div", { class: "filters" }, el("label", {}, "Category", picker)), trendHost);

    async function drawTrend() {
      const trend = await api.get(`/reports/category-trend/${state.trendCategoryId}?months=12`);
      const total = trend.months.reduce((sum, m) => sum + m.spent_cents, 0);
      trendHost.replaceChildren(
        el("div", { class: "summary-chips", style: "margin-bottom:8px" },
          el("span", {}, "Total: ", el("b", { text: fmt(-total) })),
          el("span", {}, "Monthly average: ", el("b", { text: fmt(-trend.average_cents) }))),
        trendChart(trend.months, trend.average_cents));
    }
    await drawTrend();
  }

  /* ----- top payees ----- */
  const payeeHost = el("div");
  const periodPicker = select([
    { value: "1", label: "This month" },
    { value: "3", label: "Last 3 months" },
    { value: "12", label: "Last 12 months" },
  ], state.payeeMonths);
  periodPicker.addEventListener("change", () => {
    state.payeeMonths = periodPicker.value;
    drawPayees();
  });

  async function drawPayees() {
    const rows = await api.get(`/reports/payees?months=${state.payeeMonths}&limit=15`);
    payeeHost.replaceChildren(rows.length
      ? el("div", { class: "table-scroll" }, el("table", {},
          el("thead", {}, el("tr", {},
            el("th", { text: "#" }), el("th", { text: "Payee" }),
            el("th", { class: "num", text: "Transactions" }),
            el("th", { class: "num", text: "Total spent" }))),
          el("tbody", {}, ...rows.map((row, i) => el("tr", { class: "no-hover" },
            el("td", { class: "muted", text: String(i + 1) }),
            el("td", { text: row.payee }),
            el("td", { class: "num", text: String(row.count) }),
            el("td", { class: "num neg", text: fmt(row.total_cents) }))))))
      : el("div", { class: "empty", text: "No spending with a payee in this period." }));
  }
  await drawPayees();

  const payeesCard = el("div", { class: "card" },
    el("h2", { text: "Top payees" }),
    el("div", { class: "filters" }, el("label", {}, "Period", periodPicker)),
    payeeHost);

  host.replaceChildren(
    netWorthCard,
    el("div", { class: "row" }, trendCard),
    el("div", { class: "row" }, payeesCard));
}
