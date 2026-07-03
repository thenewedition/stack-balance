"use strict";

const SVG_NS = "http://www.w3.org/2000/svg";

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  applyAttrs(node, attrs);
  for (const child of children) if (child !== null && child !== undefined && child !== false) node.append(child);
  return node;
}

export function svgEl(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG_NS, tag);
  applyAttrs(node, attrs);
  for (const child of children) if (child !== null && child !== undefined && child !== false) node.append(child);
  return node;
}

function applyAttrs(node, attrs) {
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value !== null && value !== undefined && value !== false) node.setAttribute(key, value);
  }
}

export function toast(message) {
  const node = document.getElementById("toast");
  node.textContent = message;
  node.style.display = "block";
  clearTimeout(node._t);
  node._t = setTimeout(() => (node.style.display = "none"), 2800);
}

/* ---------- shared chart tooltip (textContent only) ---------- */

export function showTooltip(event, title, rows) {
  const tooltip = document.getElementById("tooltip");
  tooltip.replaceChildren(el("div", { class: "t-title", text: title }));
  for (const row of rows) {
    const key = el("span", { class: "k" });
    if (row.color) key.append(el("span", { class: "line-key", style: `background:${row.color}` }));
    key.append(document.createTextNode(row.label));
    tooltip.append(el("div", { class: "t-row" }, key, el("span", { class: "v", text: row.value })));
  }
  tooltip.style.display = "block";
  const pad = 14;
  let x = event.clientX + pad, y = event.clientY + pad;
  if (x + tooltip.offsetWidth > innerWidth - 8) x = event.clientX - tooltip.offsetWidth - pad;
  if (y + tooltip.offsetHeight > innerHeight - 8) y = event.clientY - tooltip.offsetHeight - pad;
  tooltip.style.left = x + "px";
  tooltip.style.top = y + "px";
}

export function hideTooltip() {
  document.getElementById("tooltip").style.display = "none";
}

/* ---------- modal ---------- */

/**
 * openModal(title, bodyNode, { submitLabel, onSubmit, danger }) -> close()
 * onSubmit may return false (or throw) to keep the modal open.
 */
export function openModal(title, body, { submitLabel = "Save", onSubmit, danger = false } = {}) {
  const submit = el("button", { class: danger ? "danger" : "primary", text: submitLabel });
  const cancel = el("button", { text: "Cancel" });
  const modal = el("div", { class: "modal", role: "dialog", "aria-label": title },
    el("h3", { text: title }), body,
    el("div", { class: "actions" }, cancel, submit));
  const overlay = el("div", { class: "overlay" }, modal);
  const close = () => overlay.remove();

  cancel.addEventListener("click", close);
  overlay.addEventListener("click", (event) => { if (event.target === overlay) close(); });
  document.addEventListener("keydown", function esc(event) {
    if (event.key === "Escape") { close(); document.removeEventListener("keydown", esc); }
  });
  submit.addEventListener("click", async () => {
    if (!onSubmit) return close();
    submit.disabled = true;
    try {
      if (await onSubmit() !== false) close();
      else submit.disabled = false;
    } catch (error) {
      toast(error.message);
      submit.disabled = false;
    }
  });

  document.body.append(overlay);
  const first = modal.querySelector("input, select, textarea");
  if (first) first.focus();
  return close;
}

export function confirmModal(title, message, onConfirm, submitLabel = "Delete") {
  openModal(title, el("p", { text: message }), { submitLabel, danger: true, onSubmit: onConfirm });
}

/* ---------- small form builders ---------- */

export function field(labelText, inputNode) {
  return el("label", { class: "field" }, labelText, inputNode);
}

export function checkbox(labelText, checked = false) {
  const input = el("input", { type: "checkbox" });
  input.checked = checked;
  return { node: el("label", { class: "check" }, input, labelText), input };
}

export function select(options, value = null) {
  const node = el("select", {},
    ...options.map(o => el("option", { value: String(o.value), text: o.label })));
  if (value !== null && value !== undefined) node.value = String(value);
  return node;
}
