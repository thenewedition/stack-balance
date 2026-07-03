"use strict";

import { api } from "../api.js";
import { el, toast, field, checkbox, select } from "../dom.js";
import { fmt } from "../format.js";
import * as refdata from "../refdata.js";

const SEMANTIC_FIELDS = ["date", "amount", "debit", "credit", "payee", "memo", "category"];

export async function render(host) {
  await refdata.load();
  if (!refdata.activeAccounts().length) {
    host.replaceChildren(el("div", { class: "card" },
      el("h2", { text: "Import transactions" }),
      el("div", { class: "empty", text: "Create an account under Settings first." })));
    return;
  }

  const accountSelect = select(
    refdata.activeAccounts().map(a => ({ value: a.id, label: a.name })));
  const skipDupes = checkbox("Skip duplicates (recommended)", true);

  const fileInput = el("input", { type: "file", accept: ".csv,.json,.txt", style: "display:none" });
  const dropzone = el("div", { class: "dropzone", role: "button", tabindex: "0",
    text: "Drop a CSV or JSON export here, or click to choose a file" });
  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") fileInput.click(); });
  dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("drag"); });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("drag"));
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("drag");
    if (e.dataTransfer.files[0]) startPreview(e.dataTransfer.files[0]);
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files[0]) startPreview(fileInput.files[0]);
  });

  const resultHost = el("div");
  let currentFile = null;
  let currentMapping = null;

  async function runImport(dryRun) {
    const fields = {
      account_id: accountSelect.value,
      dry_run: String(dryRun),
      skip_duplicates: String(skipDupes.input.checked),
    };
    if (currentMapping) fields.column_mapping = JSON.stringify(currentMapping);
    return api.upload("/import", fields, currentFile);
  }

  async function startPreview(file) {
    currentFile = file;
    currentMapping = null;
    dropzone.textContent = `Selected: ${file.name} — previewing…`;
    try {
      showResult(await runImport(true));
      dropzone.textContent = `Selected: ${file.name} (drop another file to replace)`;
    } catch (error) {
      dropzone.textContent = "Drop a CSV or JSON export here, or click to choose a file";
      resultHost.replaceChildren(el("div", { class: "card" },
        el("h2", { text: "Could not parse file" }),
        el("p", { class: "error-text", text: error.message })));
    }
  }

  function showResult(result) {
    /* column mapping editors */
    const allHeaders = result.headers;
    const mappingControls = el("div", { class: "mapping-grid" });
    const mappingSelects = {};
    for (const semantic of SEMANTIC_FIELDS) {
      const options = [{ value: "", label: "— not present —" },
        ...allHeaders.map(h => ({ value: h, label: h }))];
      const control = select(options, result.column_mapping[semantic] ?? "");
      mappingSelects[semantic] = control;
      control.addEventListener("change", async () => {
        currentMapping = {};
        for (const [key, sel] of Object.entries(mappingSelects)) {
          if (sel.value) currentMapping[key] = sel.value;
        }
        try { showResult(await runImport(true)); }
        catch (error) { toast("Preview failed: " + error.message); }
      });
      mappingControls.append(el("label", { class: "field", style: "margin:0" },
        semantic, control));
    }

    const stats = el("div", { class: "summary-chips", style: "margin: 10px 0" },
      el("span", {}, "Format: ", el("b", { text: result.format.toUpperCase() })),
      el("span", {}, "Rows: ", el("b", { text: String(result.total_rows) })),
      el("span", {}, "Will import: ", el("b", { text: String(result.imported) })),
      el("span", {}, "Duplicates skipped: ", el("b", { text: String(result.skipped_duplicates) })),
      el("span", {}, "Errors: ", el("b", { text: String(result.errors.length) })));

    const previewTable = el("div", { class: "table-scroll" }, el("table", {},
      el("thead", {}, el("tr", {},
        el("th", { text: "Date" }), el("th", { text: "Payee" }), el("th", { text: "Memo" }),
        el("th", { text: "Category" }), el("th", { class: "num", text: "Amount" }),
        el("th", { text: "" }))),
      el("tbody", {}, ...result.preview.map(row => el("tr", { class: "no-hover" + (row.duplicate ? " dup" : "") },
        el("td", { text: row.date }),
        el("td", { text: row.payee || "—" }),
        el("td", { class: "muted", text: row.memo }),
        el("td", { text: row.category ?? "" }),
        el("td", { class: "num" + (row.amount_cents < 0 ? " neg" : ""), text: fmt(row.amount_cents) }),
        el("td", { text: row.duplicate ? "duplicate" : "" }))))));

    const errorList = result.errors.length
      ? el("details", {}, el("summary", { text: `${result.errors.length} row error(s)` }),
          el("ul", {}, ...result.errors.slice(0, 30).map(e =>
            el("li", { class: "error-text", text: `Row ${e.row}: ${e.error}` }))))
      : null;

    const commitButton = el("button", { class: "primary", text: `Import ${result.imported} transaction(s)` });
    commitButton.disabled = result.imported === 0;
    commitButton.addEventListener("click", async () => {
      commitButton.disabled = true;
      try {
        const final = await runImport(false);
        toast(`Imported ${final.imported} transaction(s), skipped ${final.skipped_duplicates} duplicate(s)`);
        resultHost.replaceChildren(el("div", { class: "card" },
          el("h2", { text: "Import complete" }),
          el("p", {}, `Imported ${final.imported} transaction(s) into `,
            el("b", { text: refdata.accountName(Number(accountSelect.value)) }), ". ",
            el("a", { href: "#/transactions", text: "Review them →" }))));
      } catch (error) {
        toast("Import failed: " + error.message);
        commitButton.disabled = false;
      }
    });

    resultHost.replaceChildren(el("div", { class: "card" },
      el("h2", { text: "Preview (nothing is saved yet)" }),
      el("p", { class: "muted", style: "font-size:12px" },
        "Columns were auto-detected — correct any of them below and the preview refreshes."),
      mappingControls, stats, previewTable, errorList,
      el("div", { class: "right", style: "margin-top:12px" }, commitButton)));
  }

  host.replaceChildren(
    el("div", { class: "card" },
      el("h2", { text: "Import transactions" }),
      el("div", { class: "filters" },
        el("label", {}, "Into account", accountSelect),
        el("label", {}, " ", skipDupes.node)),
      dropzone,
      el("p", { class: "muted", style: "font-size:12px" },
        "Works with exports from any bank: delimiter, date format, amount format, and column names are auto-detected (including separate debit/credit columns). Re-importing the same file is safe — duplicates are skipped.")),
    resultHost, fileInput);
}
