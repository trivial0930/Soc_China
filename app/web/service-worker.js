// Minimal SW: cache the app shell only (never API data, to keep demo fresh).
const SHELL = "lab-admin-shell-v1";
const ASSETS = [
  "./", "./index.html", "./css/app.css",
  "./js/api.js", "./js/alerts.js", "./js/stations.js", "./js/reports.js", "./js/assets.js", "./js/app.js",
  "./manifest.webmanifest",
];
self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) =>
    Promise.all(ks.filter((k) => k !== SHELL).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  // never cache API / images / SSE — always go to network
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/img/") || url.pathname.startsWith("/events/")) {
    return; // default network fetch
  }
  e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request)));
});
