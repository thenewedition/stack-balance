/* Stack Balance service worker.
 *
 * Strategy:
 * - App shell (/ and /static/*): cache-first, refreshed in the background,
 *   so the app opens instantly and works offline.
 * - API GETs: network-first with cache fallback — live data when online,
 *   last-known data when offline.
 * - Everything else (API writes, /docs): network only. Writes must never be
 *   replayed from a cache.
 */
"use strict";

const CACHE = "stack-balance-v1";
const SHELL = [
  "/",
  "/static/css/app.css",
  "/static/js/app.js",
  "/static/js/api.js",
  "/static/js/dom.js",
  "/static/js/format.js",
  "/static/js/charts.js",
  "/static/js/refdata.js",
  "/static/js/views/dashboard.js",
  "/static/js/views/budget.js",
  "/static/js/views/transactions.js",
  "/static/js/views/import.js",
  "/static/js/views/reports.js",
  "/static/js/views/settings.js",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

async function cacheFirst(request) {
  const cached = await caches.match(request);
  const refresh = fetch(request)
    .then((response) => {
      if (response.ok) {
        const copy = response.clone();
        caches.open(CACHE).then((cache) => cache.put(request, copy));
      }
      return response;
    })
    .catch(() => cached);
  return cached || refresh;
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const copy = response.clone();
      caches.open(CACHE).then((cache) => cache.put(request, copy));
    }
    return response;
  } catch (error) {
    const cached = await caches.match(request);
    if (cached) return cached;
    throw error;
  }
}

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== location.origin) return;

  if (url.pathname === "/" || url.pathname.startsWith("/static/")
      || url.pathname === "/manifest.webmanifest") {
    event.respondWith(cacheFirst(event.request));
  } else if (url.pathname.startsWith("/api/") && !url.pathname.startsWith("/api/backups/")) {
    event.respondWith(networkFirst(event.request));
  }
  // /docs, backup downloads, and non-GET requests go straight to the network.
});
