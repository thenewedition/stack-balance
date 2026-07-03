"use strict";

export const fmt = (cents) => {
  const sign = cents < 0 ? "−" : "";
  return sign + "$" + (Math.abs(cents) / 100).toLocaleString(undefined,
    { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

export const fmtCompact = (cents) => {
  const value = Math.abs(cents) / 100;
  const sign = cents < 0 ? "−" : "";
  if (value >= 1_000_000) return sign + "$" + (value / 1_000_000).toFixed(1) + "M";
  if (value >= 10_000) return sign + "$" + (value / 1000).toFixed(1) + "K";
  return sign + "$" + value.toLocaleString(undefined, { maximumFractionDigits: 0 });
};

/** "12.34", "$1,234.5", "-20" -> integer cents; NaN when unparseable. */
export const parseDollars = (text) => {
  const cleaned = String(text).replace(/[$,\s]/g, "").replace("−", "-");
  if (cleaned === "" || Number.isNaN(Number(cleaned))) return NaN;
  return Math.round(Number(cleaned) * 100);
};

export const centsToInput = (cents) => (cents / 100).toFixed(2);

export const currentMonth = () => {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
};

export const monthAdd = (month, delta) => {
  const [y, m] = month.split("-").map(Number);
  const index = y * 12 + (m - 1) + delta;
  return `${Math.floor(index / 12).toString().padStart(4, "0")}-${String(index % 12 + 1).padStart(2, "0")}`;
};

export const monthLabel = (month) =>
  new Date(month + "-15").toLocaleDateString(undefined, { month: "long", year: "numeric" });

export const monthShort = (month) =>
  new Date(month + "-15").toLocaleDateString(undefined, { month: "short", year: "numeric" });

export const today = () => new Date().toISOString().slice(0, 10);
