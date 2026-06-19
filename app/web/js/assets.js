// 物资定位 query (lower priority).
const Assets = (() => {
  let cat = "";
  function results(items) {
    if (!items.length) return `<div class="empty">未找到物资</div>`;
    return items.map((a) => `<div class="card">
      <div class="row"><strong>${API.esc(a.name)}</strong>
        <span class="badge ${a.category === "large" ? "b-info" : "b-ok"}">${a.category === "large" ? "设备" : "耗材"}</span></div>
      <div class="meta">📍 ${API.esc(a.location_text)}${a.quantity ? "　×" + a.quantity : ""}${a.note ? "　" + API.esc(a.note) : ""}</div>
    </div>`).join("");
  }
  async function search() {
    const q = document.getElementById("assetQ").value.trim();
    const box = document.getElementById("assetRes");
    box.innerHTML = `<div class="loading">查询中…</div>`;
    try {
      let url = "/api/assets?limit=100";
      if (q) url += "&name=" + encodeURIComponent(q);
      if (cat) url += "&category=" + cat;
      box.innerHTML = results((await API.getJSON(url)).items);
    } catch (e) { box.innerHTML = `<div class="empty">查询失败</div>`; }
  }
  function setCat(c) { cat = c; render(document.getElementById("app")); }
  async function render(app) {
    app.innerHTML = `<div class="searchbar">
        <input id="assetQ" placeholder="搜设备/耗材名,如 示波器、电阻" onkeydown="if(event.key==='Enter')Assets.search()">
        <button class="btn" onclick="Assets.search()">查询</button></div>
      <div class="filters">
        ${[["", "全部"], ["large", "大型设备"], ["small", "小型耗材"]].map(([k, t]) =>
          `<span class="chip ${cat === k ? "on" : ""}" onclick="Assets.setCat('${k}')">${t}</span>`).join("")}</div>
      <div id="assetRes"></div>`;
    search();
  }
  return { render, search, setCat };
})();
