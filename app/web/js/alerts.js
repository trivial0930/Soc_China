// Feature 1: real-time safety alerts. List + SSE live push + handle.
const Alerts = (() => {
  let events = [];
  let mounted = false;
  let filter = ""; // "" | critical | warning | unhandled

  function card(e) {
    const sev = API.finalSev(e);
    const expl = e.brief && e.brief.explanation ? e.brief.explanation : "";
    const thumb = e.image ? `<img class="thumb" loading="lazy" src="${API.imgUrl(e.image)}" alt="">` : "";
    const handled = e.handled
      ? `<span class="handled-tag">✓ 已处理${e.handled_note ? "：" + API.esc(e.handled_note) : ""}</span>`
      : `<button class="btn" onclick="Alerts.handle('${API.esc(e.event_id)}')">处理</button>`;
    return `<div class="card ${sev}" id="ev-${API.esc(e.event_id)}">
      <div class="row">
        <span class="badge b-${sev}">${API.sevText[sev] || sev}</span>
        <span class="meta">${API.esc(e.station_id)} · ${API.fmtIso(e.timestamp)}</span>
      </div>
      <div class="summary">${API.esc(e.summary)}</div>
      ${expl ? `<div class="meta">${API.esc(expl)}</div>` : ""}
      ${thumb}
      <div class="row" style="margin-top:10px"><span></span>${handled}</div>
    </div>`;
  }

  function matches(e) {
    if (filter === "critical") return API.finalSev(e) === "critical";
    if (filter === "warning") return API.finalSev(e) === "warning";
    if (filter === "unhandled") return !e.handled;
    return true;
  }

  function list() {
    const rows = events.filter(matches);
    return rows.length ? rows.map(card).join("") : `<div class="empty">暂无告警</div>`;
  }

  function chips() {
    const opt = [["", "全部"], ["unhandled", "未处理"], ["critical", "严重"], ["warning", "警告"]];
    return `<div class="filters">` + opt.map(([k, t]) =>
      `<span class="chip ${filter === k ? "on" : ""}" onclick="Alerts.setFilter('${k}')">${t}</span>`).join("") + `</div>`;
  }

  function paint() {
    if (!mounted) return;
    const c = document.getElementById("alertList");
    if (c) c.innerHTML = list();
  }

  async function render(app) {
    mounted = true;
    app.innerHTML = chips() + `<div id="alertList"><div class="loading">加载中…</div></div>`;
    try {
      const d = await API.getJSON("/api/events?limit=100");
      events = d.items;
    } catch (e) { events = []; }
    paint(); updateBadge();
  }

  function setFilter(f) { filter = f; render(document.getElementById("app")); }

  async function handle(id) {
    const note = prompt("处理备注(如:已断电并提醒学生)", "已处理");
    if (note === null) return;
    try {
      const e = await API.post(`/api/events/${id}/handle`, { note });
      upsert(e); paint(); updateBadge();
    } catch (err) {
      if (err.status === 401) {           // backend requires a write token
        const t = prompt("该后端要求写权限令牌(Authorization token):", API.getToken());
        if (t) { API.setToken(t); return handle(id); }  // retry once with the token
        return;
      }
      alert("处理失败:" + err.message);
    }
  }

  function upsert(e) {
    const i = events.findIndex((x) => x.event_id === e.event_id);
    if (i >= 0) events[i] = { ...events[i], ...e };
    else events.unshift(e);
  }

  // called by app.js on SSE
  function onLive(name, payload) {
    if (name === "hazard") {
      upsert(payload);
      const sev = API.finalSev(payload);
      if (sev === "critical" && "Notification" in window && Notification.permission === "granted") {
        new Notification("严重告警 · " + payload.station_id, { body: payload.summary });
      }
    } else if (name === "handled") {
      const i = events.findIndex((x) => x.event_id === payload.event_id);
      if (i >= 0) events[i] = { ...events[i], handled: true, handled_at: payload.handled_at, handled_note: payload.handled_note };
    }
    paint(); updateBadge();
  }

  function updateBadge() {
    const n = events.filter((e) => !e.handled && API.finalSev(e) !== "info").length;
    const b = document.getElementById("alertBadge");
    if (b) { b.textContent = n; b.classList.toggle("hidden", n === 0); }
  }

  // seed events even when not on the alerts tab, so the badge is live
  async function prime() {
    try { events = (await API.getJSON("/api/events?limit=100")).items; updateBadge(); } catch (_) {}
  }

  return { render, setFilter, handle, onLive, updateBadge, prime, _unmount: () => (mounted = false) };
})();
