// Feature 3: inspection reports — list + detail (minimal markdown render).
const Reports = (() => {
  // tiny markdown -> html (headings, bold, ul, hr, blockquote, paragraphs)
  function md(src) {
    const lines = String(src || "").split("\n");
    let html = "", inList = false;
    const inline = (t) => API.esc(t)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/`(.+?)`/g, "<code>$1</code>");
    const closeList = () => { if (inList) { html += "</ul>"; inList = false; } };
    for (let raw of lines) {
      const l = raw.replace(/\s+$/, "");
      if (/^###\s+/.test(l)) { closeList(); html += `<h3>${inline(l.replace(/^###\s+/, ""))}</h3>`; }
      else if (/^##\s+/.test(l)) { closeList(); html += `<h2>${inline(l.replace(/^##\s+/, ""))}</h2>`; }
      else if (/^#\s+/.test(l)) { closeList(); html += `<h1>${inline(l.replace(/^#\s+/, ""))}</h1>`; }
      else if (/^---+$/.test(l)) { closeList(); html += "<hr>"; }
      else if (/^>\s?/.test(l)) { closeList(); html += `<blockquote>${inline(l.replace(/^>\s?/, ""))}</blockquote>`; }
      else if (/^[-*]\s+/.test(l)) { if (!inList) { html += "<ul>"; inList = true; } html += `<li>${inline(l.replace(/^[-*]\s+/, ""))}</li>`; }
      else if (l.trim() === "") { closeList(); }
      else { closeList(); html += `<p>${inline(l)}</p>`; }
    }
    closeList();
    return html;
  }

  function vbadge(v) { return v ? `<span class="badge b-${v}">${v}</span>` : ""; }

  async function render(app) {
    app.innerHTML = `<div id="repList"><div class="loading">加载中…</div></div>`;
    try {
      const d = await API.getJSON("/api/reports?limit=100");
      document.getElementById("repList").innerHTML = d.items.length
        ? d.items.map((r) => `<div class="card" onclick="Reports.open(${r.id})">
            <div class="row"><strong>${API.esc(r.title)}</strong>${vbadge(r.verdict)}</div>
            <div class="meta">${API.esc(r.report_type)} · ${API.fmtIso(r.created_at)} · ${r.event_ids.length} 个事件</div>
          </div>`).join("")
        : `<div class="empty">暂无报告</div>`;
    } catch (e) { document.getElementById("repList").innerHTML = `<div class="empty">加载失败</div>`; }
  }

  async function open(id) {
    const app = document.getElementById("app");
    app.innerHTML = `<button class="back" onclick="Reports.render(document.getElementById('app'))">‹ 返回报告列表</button>
      <div id="repBody"><div class="loading">加载中…</div></div>`;
    try {
      const r = await API.getJSON("/api/reports/" + id);
      document.getElementById("repBody").innerHTML = `<div class="report-body">${md(r.body_markdown)}</div>`;
    } catch (e) { document.getElementById("repBody").innerHTML = `<div class="empty">加载失败</div>`; }
  }

  return { render, open, _md: md };
})();
