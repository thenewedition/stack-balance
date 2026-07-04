"use strict";

import { toast } from "./dom.js";
import * as dashboard from "./views/dashboard.js";
import * as budget from "./views/budget.js";
import * as transactions from "./views/transactions.js";
import * as importer from "./views/import.js";
import * as reports from "./views/reports.js";
import * as settings from "./views/settings.js";

const routes = {
  "": dashboard,
  "budget": budget,
  "transactions": transactions,
  "import": importer,
  "reports": reports,
  "settings": settings,
};

async function render() {
  const hash = location.hash.replace(/^#\/?/, "").split("?")[0].split("/")[0];
  const view = routes[hash] ?? dashboard;

  for (const link of document.querySelectorAll("#nav a")) {
    const target = link.getAttribute("href").replace(/^#\/?/, "");
    link.classList.toggle("active", target === (routes[hash] ? hash : ""));
  }

  const host = document.getElementById("view");
  host.replaceChildren();
  try {
    await view.render(host);
  } catch (error) {
    toast("Failed to load view: " + error.message);
    console.error(error);
  }
}

addEventListener("hashchange", render);
render();

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {
    /* offline support unavailable (e.g. non-secure context) — app still works */
  });
}
