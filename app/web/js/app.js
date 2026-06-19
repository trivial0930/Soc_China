// Router + bottom nav + global SSE wiring.
const ROUTES = {
  "/alerts": Alerts, "/stations": Stations, "/reports": Reports, "/assets": Assets,
};

function route() {
  const hash = location.hash.replace(/^#/, "") || "/alerts";
  const view = ROUTES[hash] || Alerts;
  document.querySelectorAll(".bottomnav a").forEach((a) =>
    a.classList.toggle("active", a.getAttribute("href") === "#" + hash));
  if (Alerts._unmount) Alerts._unmount();
  view.render(document.getElementById("app"));
}

window.addEventListener("hashchange", route);

window.addEventListener("DOMContentLoaded", () => {
  if (!location.hash) location.hash = "/alerts";
  // ask notification permission for live critical alerts
  if ("Notification" in window && Notification.permission === "default") {
    Notification.requestPermission().catch(() => {});
  }
  // global SSE: feeds the alerts module + badge regardless of current tab
  API.streamEvents((name, payload) => Alerts.onLive(name, payload));
  Alerts.prime(); // load events for the badge even if first tab isn't alerts
  route();
  // service worker (no-install / add to home screen)
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("service-worker.js").catch(() => {});
});
