// API layer: fetch wrappers + SSE + small helpers. Same-origin (served by backend).
const API = (() => {
  const base = ""; // relative; PWA is served by the backend

  async function getJSON(path) {
    const r = await fetch(base + path);
    if (!r.ok) throw new Error(path + " -> " + r.status);
    return r.json();
  }
  async function post(path, body) {
    const r = await fetch(base + path, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    if (!r.ok) throw new Error(path + " -> " + r.status);
    return r.json();
  }

  // SSE with auto-reconnect; onEvent(name, payload)
  function streamEvents(onEvent) {
    let es;
    function connect() {
      es = new EventSource(base + "/events/stream");
      es.onopen = () => setConn(true);
      es.onerror = () => { setConn(false); }; // EventSource auto-reconnects
      ["hazard", "handled"].forEach((ev) =>
        es.addEventListener(ev, (e) => {
          try { onEvent(ev, JSON.parse(e.data).payload); } catch (_) {}
        }));
    }
    connect();
    return () => es && es.close();
  }

  function setConn(ok) {
    const d = document.getElementById("conn");
    if (d) d.className = "dot " + (ok ? "on" : "off");
  }

  // helpers
  const sevClass = (s) => (s === "critical" || s === "warning" || s === "info") ? s : "info";
  const sevText = { info: "信息", warning: "警告", critical: "严重" };
  const imgUrl = (name) => name ? base + "/img/" + encodeURIComponent(name) : "";
  function fmtIso(s) {
    if (!s) return "";
    try { return new Date(s).toLocaleString("zh-CN", { hour12: false }); } catch (_) { return s; }
  }
  function fmtUnix(sec) {
    if (!sec) return "—";
    try { return new Date(sec * 1000).toLocaleString("zh-CN", { hour12: false }); } catch (_) { return String(sec); }
  }
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  return { getJSON, post, streamEvents, sevClass, sevText, imgUrl, fmtIso, fmtUnix, esc };
})();
