// API layer: fetch wrappers + SSE + small helpers. Same-origin (served by backend).
const API = (() => {
  const base = ""; // relative; PWA is served by the backend

  async function getJSON(path) {
    const r = await fetch(base + path);
    if (!r.ok) throw new Error(path + " -> " + r.status);
    return r.json();
  }
  function getToken() { try { return localStorage.getItem("app_token") || ""; } catch (_) { return ""; } }
  function setToken(t) { try { localStorage.setItem("app_token", t || ""); } catch (_) {} }

  async function post(path, body) {
    const headers = { "Content-Type": "application/json" };
    const tok = getToken();
    if (tok) headers["Authorization"] = "Bearer " + tok; // write endpoints may require a token (SPEC §4.1)
    const r = await fetch(base + path, { method: "POST", headers, body: JSON.stringify(body || {}) });
    if (!r.ok) { const e = new Error(path + " -> " + r.status); e.status = r.status; throw e; }
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
  // final severity = L2-confirmed (in brief) if present, else L1 severity.
  // List endpoints omit brief; SSE 'hazard' may carry brief -> corrected value then.
  const finalSev = (e) => sevClass((e.brief && e.brief.confirmed_severity) || e.severity);
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

  return { getJSON, post, streamEvents, sevClass, finalSev, sevText, imgUrl, fmtIso, fmtUnix, esc, getToken, setToken };
})();
