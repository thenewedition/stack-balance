"use strict";

import { el, svgEl, showTooltip, hideTooltip } from "./dom.js";
import { fmt, fmtCompact, monthShort } from "./format.js";

function niceStep(maxValue, ticks = 4) {
  const rough = maxValue / ticks;
  const power = Math.pow(10, Math.floor(Math.log10(rough || 1)));
  for (const multiplier of [1, 2, 2.5, 5, 10]) {
    if (rough <= multiplier * power) return multiplier * power;
  }
  return 10 * power;
}

/** Rounded-top column path (4px data-end radius, square baseline). */
function columnPath(x, width, yTop, yBase) {
  const r = Math.min(4, yBase - yTop);
  return `M${x},${yBase} V${yTop + r} Q${x},${yTop} ${x + r},${yTop}` +
         ` H${x + width - r} Q${x + width},${yTop} ${x + width},${yTop + r} V${yBase} Z`;
}

/** Rounded-right horizontal bar path. */
function hbarPath(x, yMid, length, halfH) {
  const r = Math.min(4, length);
  return `M${x},${yMid - halfH} H${x + length - r} Q${x + length},${yMid - halfH} ${x + length},${yMid - halfH + r}` +
         ` V${yMid + halfH - r} Q${x + length},${yMid + halfH} ${x + length - r},${yMid + halfH} H${x} Z`;
}

/** Grouped income/spending columns per month with net in the tooltip. */
export function cashFlowChart(months) {
  const width = 640, height = 240, top = 12, bottom = 26, left = 52, right = 8;
  const plotW = width - left - right, plotH = height - top - bottom;
  const maxValue = Math.max(100, ...months.map(m => Math.max(m.income_cents, -m.expense_cents)));
  const step = niceStep(maxValue);
  const yMax = Math.ceil(maxValue / step) * step;
  const y = (v) => top + plotH - (v / yMax) * plotH;

  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, width: "100%", role: "img",
    "aria-label": "Monthly income and spending" });

  for (let tick = 0; tick <= yMax; tick += step) {
    svg.append(svgEl("line", { x1: left, x2: width - right, y1: y(tick), y2: y(tick),
      stroke: tick === 0 ? "var(--baseline)" : "var(--grid)", "stroke-width": 1 }));
    svg.append(svgEl("text", { x: left - 6, y: y(tick) + 4, "text-anchor": "end",
      text: fmtCompact(tick) }));
  }

  const band = plotW / months.length;
  const gap = 2, groupPad = Math.max(band * 0.18, 6);
  const barW = Math.min(24, (band - groupPad * 2 - gap) / 2);
  const style = getComputedStyle(document.documentElement);
  const incomeColor = style.getPropertyValue("--income").trim();
  const expenseColor = style.getPropertyValue("--expense").trim();

  months.forEach((m, i) => {
    const x0 = left + i * band;
    const cx = x0 + band / 2;
    for (const bar of [
      { v: m.income_cents, color: "var(--income)", x: cx - gap / 2 - barW },
      { v: -m.expense_cents, color: "var(--expense)", x: cx + gap / 2 },
    ]) {
      if (bar.v <= 0) continue;
      svg.append(svgEl("path", { d: columnPath(bar.x, barW, y(bar.v), y(0)), fill: bar.color }));
    }
    if (i % 2 === 0 || months.length <= 6) {
      const label = new Date(m.month + "-15").toLocaleDateString(undefined, { month: "short" }) +
        (m.month.endsWith("-01") || i === 0 ? " ’" + m.month.slice(2, 4) : "");
      svg.append(svgEl("text", { x: cx, y: height - 8, "text-anchor": "middle", text: label }));
    }
    const hit = svgEl("rect", { x: x0, y: top, width: band, height: plotH + bottom, fill: "transparent" });
    hit.addEventListener("pointermove", (event) => showTooltip(event, monthShort(m.month), [
      { label: "Income", value: fmt(m.income_cents), color: incomeColor },
      { label: "Spending", value: fmt(m.expense_cents), color: expenseColor },
      { label: "Net", value: fmt(m.net_cents) },
    ]));
    hit.addEventListener("pointerleave", hideTooltip);
    svg.append(hit);
  });
  return svg;
}

/** Horizontal magnitude bars, single sequential hue. rows: [{name, spent_cents}] */
export function spendingChart(rows) {
  const top = rows.slice(0, 8);
  const maxSpend = Math.max(...top.map(r => -r.spent_cents));
  const rowH = 30, labelW = 130, valueW = 66, width = 460;
  const barMax = width - labelW - valueW;
  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${top.length * rowH}`, width: "100%",
    role: "img", "aria-label": "Spending by category" });
  top.forEach((row, i) => {
    const yMid = i * rowH + rowH / 2;
    const barLen = Math.max((-row.spent_cents / maxSpend) * barMax, 2);
    svg.append(svgEl("text", { x: labelW - 8, y: yMid + 4, "text-anchor": "end",
      fill: "var(--text-secondary)", text: row.name }));
    svg.append(svgEl("path", { d: hbarPath(labelW, yMid, barLen, 8), fill: "var(--seq)" }));
    svg.append(svgEl("text", { x: labelW + barLen + 6, y: yMid + 4,
      fill: "var(--text-secondary)", text: fmtCompact(-row.spent_cents) }));
    const hit = svgEl("rect", { x: 0, y: i * rowH, width, height: rowH, fill: "transparent" });
    hit.addEventListener("pointermove", (event) =>
      showTooltip(event, row.name, [{ label: "Spent", value: fmt(-row.spent_cents) }]));
    hit.addEventListener("pointerleave", hideTooltip);
    svg.append(hit);
  });
  return svg;
}

/** Progress meter (track = lighter step of the same ramp). */
export function meter(percent) {
  return el("div", { class: "meter" },
    el("div", { style: `width:${Math.min(percent, 100)}%` }));
}

/** Net worth line (single series: 2px line + 10% area wash + crosshair tooltip). */
export function netWorthChart(months) {
  const width = 640, height = 240, top = 14, bottom = 26, left = 56, right = 14;
  const plotW = width - left - right, plotH = height - top - bottom;
  const values = months.map(m => m.net_cents);
  const rawMin = Math.min(0, ...values), rawMax = Math.max(100, ...values);
  const step = niceStep(rawMax - rawMin || 100);
  const yMin = Math.floor(rawMin / step) * step;
  const yMax = Math.ceil(rawMax / step) * step;
  const y = (v) => top + plotH - ((v - yMin) / (yMax - yMin)) * plotH;
  const x = (i) => months.length === 1 ? left + plotW / 2
    : left + (i / (months.length - 1)) * plotW;

  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, width: "100%",
    role: "img", "aria-label": "Net worth over time" });

  for (let tick = yMin; tick <= yMax; tick += step) {
    svg.append(svgEl("line", { x1: left, x2: width - right, y1: y(tick), y2: y(tick),
      stroke: tick === 0 ? "var(--baseline)" : "var(--grid)", "stroke-width": 1 }));
    svg.append(svgEl("text", { x: left - 6, y: y(tick) + 4, "text-anchor": "end",
      text: fmtCompact(tick) }));
  }
  months.forEach((m, i) => {
    if (i % 2 === 0 || months.length <= 6) {
      const label = new Date(m.month + "-15").toLocaleDateString(undefined, { month: "short" }) +
        (m.month.endsWith("-01") || i === 0 ? " ’" + m.month.slice(2, 4) : "");
      svg.append(svgEl("text", { x: x(i), y: height - 8, "text-anchor": "middle", text: label }));
    }
  });

  const linePoints = months.map((m, i) => `${x(i)},${y(m.net_cents)}`).join(" ");
  svg.append(svgEl("polygon", {
    points: `${x(0)},${y(Math.max(yMin, 0))} ${linePoints} ${x(months.length - 1)},${y(Math.max(yMin, 0))}`,
    fill: "var(--seq)", opacity: "0.1" }));
  svg.append(svgEl("polyline", { points: linePoints, fill: "none",
    stroke: "var(--seq)", "stroke-width": 2,
    "stroke-linejoin": "round", "stroke-linecap": "round" }));
  const last = months[months.length - 1];
  svg.append(svgEl("circle", { cx: x(months.length - 1), cy: y(last.net_cents), r: 4,
    fill: "var(--seq)", stroke: "var(--surface-1)", "stroke-width": 2 }));

  // crosshair + tooltip: snap to nearest month
  const crosshair = svgEl("line", { y1: top, y2: top + plotH, stroke: "var(--baseline)",
    "stroke-width": 1, visibility: "hidden" });
  svg.append(crosshair);
  const hit = svgEl("rect", { x: left, y: top, width: plotW, height: plotH + bottom,
    fill: "transparent" });
  hit.addEventListener("pointermove", (event) => {
    const box = svg.getBoundingClientRect();
    const px = (event.clientX - box.left) / box.width * width;
    const i = Math.max(0, Math.min(months.length - 1,
      Math.round((px - left) / (plotW / Math.max(months.length - 1, 1)))));
    crosshair.setAttribute("x1", x(i));
    crosshair.setAttribute("x2", x(i));
    crosshair.setAttribute("visibility", "visible");
    const m = months[i];
    showTooltip(event, monthShort(m.month), [
      { label: "Assets", value: fmt(m.assets_cents) },
      { label: "Debts", value: fmt(m.debts_cents) },
      { label: "Net worth", value: fmt(m.net_cents) },
    ]);
  });
  hit.addEventListener("pointerleave", () => {
    crosshair.setAttribute("visibility", "hidden");
    hideTooltip();
  });
  svg.append(hit);
  return svg;
}

/** Monthly columns for one category (sequential hue) + average reference line. */
export function trendChart(months, averageCents) {
  const width = 640, height = 220, top = 14, bottom = 26, left = 52, right = 70;
  const plotW = width - left - right, plotH = height - top - bottom;
  const magnitudes = months.map(m => -m.spent_cents);
  const maxValue = Math.max(100, ...magnitudes);
  const step = niceStep(maxValue);
  const yMax = Math.ceil(maxValue / step) * step;
  const y = (v) => top + plotH - (v / yMax) * plotH;

  const svg = svgEl("svg", { viewBox: `0 0 ${width} ${height}`, width: "100%",
    role: "img", "aria-label": "Monthly spending trend" });
  for (let tick = 0; tick <= yMax; tick += step) {
    svg.append(svgEl("line", { x1: left, x2: width - right, y1: y(tick), y2: y(tick),
      stroke: tick === 0 ? "var(--baseline)" : "var(--grid)", "stroke-width": 1 }));
    svg.append(svgEl("text", { x: left - 6, y: y(tick) + 4, "text-anchor": "end",
      text: fmtCompact(tick) }));
  }

  const band = plotW / months.length;
  const barW = Math.min(24, band * 0.55);
  months.forEach((m, i) => {
    const cx = left + i * band + band / 2;
    const value = -m.spent_cents;
    if (value > 0) {
      svg.append(svgEl("path", { d: columnPath(cx - barW / 2, barW, y(value), y(0)),
        fill: "var(--seq)" }));
    }
    if (i % 2 === 0 || months.length <= 6) {
      const label = new Date(m.month + "-15").toLocaleDateString(undefined, { month: "short" }) +
        (m.month.endsWith("-01") || i === 0 ? " ’" + m.month.slice(2, 4) : "");
      svg.append(svgEl("text", { x: cx, y: height - 8, "text-anchor": "middle", text: label }));
    }
    const hit = svgEl("rect", { x: left + i * band, y: top, width: band,
      height: plotH + bottom, fill: "transparent" });
    hit.addEventListener("pointermove", (event) =>
      showTooltip(event, monthShort(m.month), [{ label: "Spent", value: fmt(-m.spent_cents) }]));
    hit.addEventListener("pointerleave", hideTooltip);
    svg.append(hit);
  });

  const avg = -averageCents;
  if (avg > 0 && avg <= yMax) {
    svg.append(svgEl("line", { x1: left, x2: width - right, y1: y(avg), y2: y(avg),
      stroke: "var(--baseline)", "stroke-width": 1 }));
    svg.append(svgEl("text", { x: width - right + 4, y: y(avg) + 4,
      text: "avg " + fmtCompact(avg) }));
  }
  return svg;
}
