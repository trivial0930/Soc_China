// Feature 2: workstation occupancy records + post-class desk acceptance.
const Stations = (() => {
  function vbadge(v) {
    return v ? `<span class="badge b-${v}">${v}</span>` : "";
  }
  function gallery(snaps) {
    if (!snaps || !snaps.length) return "";
    return `<div class="gallery">` + snaps.map((s) =>
      `<img loading="lazy" src="${API.imgUrl(s)}" alt="">`).join("") + `</div>`;
  }

  function recCard(r) {
    return `<div class="card" onclick="Stations.detail('${API.esc(r.station_id)}')">
      <div class="row">
        <strong>${API.esc(r.station_id)}</strong>
        ${vbadge(r.acceptance_hint)}
      </div>
      <div class="meta">进入 ${API.fmtUnix(r.entered_at)}　离开 ${API.fmtUnix(r.left_at)}</div>
      ${r.note ? `<div class="meta">${API.esc(r.note)}</div>` : ""}
      ${gallery(r.snapshots)}
    </div>`;
  }

  async function render(app) {
    app.innerHTML = `<div id="recList"><div class="loading">加载中…</div></div>`;
    try {
      const d = await API.getJSON("/api/records?limit=100");
      document.getElementById("recList").innerHTML =
        d.items.length ? d.items.map(recCard).join("") : `<div class="empty">暂无工位记录</div>`;
    } catch (e) {
      document.getElementById("recList").innerHTML = `<div class="empty">加载失败</div>`;
    }
  }

  async function detail(station) {
    const app = document.getElementById("app");
    app.innerHTML = `<button class="back" onclick="Stations.render(document.getElementById('app'))">‹ 返回工位列表</button>
      <div id="stDetail"><div class="loading">加载中…</div></div>`;
    try {
      const d = await API.getJSON("/api/stations/" + encodeURIComponent(station));
      const acc = d.latest_acceptance;
      const rec = d.latest_record;
      let html = `<h2 style="margin:4px 0 12px">${API.esc(station)}</h2>`;
      if (acc) {
        html += `<div class="card ${API.sevClass(acc.severity)}">
          <div class="row"><strong>课后验收</strong>${vbadge(acc.verdict)}</div>
          ${acc.problems && acc.problems.length
            ? `<ul style="margin:6px 0 0;padding-left:20px">` + acc.problems.map((p) => `<li>${API.esc(p)}</li>`).join("") + `</ul>`
            : `<div class="meta">无问题</div>`}</div>`;
      }
      if (rec) {
        html += `<div class="card"><div class="meta">最近占用 ${API.fmtUnix(rec.entered_at)} — ${API.fmtUnix(rec.left_at)}</div>
          ${rec.note ? `<div class="meta">${API.esc(rec.note)}</div>` : ""}${gallery(rec.snapshots)}</div>`;
      }
      if (d.recent_events && d.recent_events.length) {
        html += `<h3 style="margin:14px 0 6px">近期告警</h3>` + d.recent_events.map((e) =>
          `<div class="card ${API.sevClass(e.severity)}"><div class="row">
            <span class="badge b-${API.sevClass(e.severity)}">${API.sevText[API.sevClass(e.severity)]}</span>
            <span class="meta">${API.fmtIso(e.timestamp)}</span></div>
            <div>${API.esc(e.summary)}</div></div>`).join("");
      }
      document.getElementById("stDetail").innerHTML = html || `<div class="empty">暂无数据</div>`;
    } catch (e) {
      document.getElementById("stDetail").innerHTML = `<div class="empty">加载失败</div>`;
    }
  }

  return { render, detail };
})();
