// LibXNDR explorer: shelf, book, atlas, ask, gold. Plain JS, no dependencies.
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const view = $("#view");
const tip = $("#tip");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const api = async (path, opts) => {
  const r = await fetch(path, opts);
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
};
const PALETTE = ["#3b6ea5", "#b5651d", "#4b8b3b", "#8e44ad", "#c0392b", "#16808a", "#a67c00", "#5d6d7e"];
const state = { books: [], color: {}, title: {}, atlas: null, lastAsk: null };
const norm = (s) => String(s).toLowerCase().replace(/[‘’]/g, "'").replace(/[“”]/g, '"')
  .replace(/[—–]/g, "-").replace(/(\w)-\s*\n\s*(\w)/g, "$1$2").replace(/\s+/g, " ").trim();
const TYPE_COLOR = { instruction: "#2e8b57", argument: "#3b6ea5", consolation: "#8e44ad", definition: "#b8860b",
  example: "#c0392b", story: "#d2691e", other: "var(--z-other)" };
const TYPES = Object.keys(TYPE_COLOR);
const unitColor = (u, byType) => byType && u.type ? TYPE_COLOR[u.type] || "var(--z-other)" : zoneColor(u);
const zoneColor = (u) => u.voice === "commentary" ? "var(--z-comment)" : u.zone === "primary" ? "var(--z-author)"
  : u.zone === "apparatus" ? "var(--z-apparatus)" : "var(--z-other)";
const short = (t) => (t || "").replace(/^The /, "").replace(/ By .*$| by .*$/i, "").slice(0, 46);
const STOP = new Set("a an the of to and or is are was were be in on at for with by as it this that what which who how why when where do does did i my we you he she they his her their should would could can about says say there than so not no".split(" "));

async function init() {
  const [books, status] = await Promise.all([api("/api/books"), api("/api/status")]);
  state.books = books;
  books.forEach((b, i) => { state.color[b.id] = PALETTE[i % PALETTE.length]; state.title[b.id] = b.title; });
  $("#status").textContent = ["bm25", status.dense && "dense", status.rerank && "rerank"].filter(Boolean).join(" + ")
    + ` · ${status.vectors} vectors`;
  $("#askform").addEventListener("submit", (e) => { e.preventDefault(); const q = $("#askq").value.trim(); if (q) location.hash = "#/ask?q=" + encodeURIComponent(q); });
  window.addEventListener("hashchange", route);
  route();
}

function route() {
  const h = location.hash || "#/";
  const [path, query] = h.slice(1).split("?");
  const qs = new URLSearchParams(query || "");
  document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("on",
    (a.dataset.nav === "shelf" && (path === "/" || path.startsWith("/book"))) || path === "/" + a.dataset.nav));
  tip.hidden = true;
  if (path !== "/ask") $("#askq").value = qs.get("q") || "";
  if (path.startsWith("/book/")) return renderBook(decodeURIComponent(path.slice(6)), qs.get("u"), qs.get("q"));
  if (path === "/atlas") return renderAtlas(qs.get("q"));
  if (path === "/ask") return renderAsk(qs.get("q") || "");
  if (path === "/gold") return renderGold(qs.get("type"));
  return renderShelf();
}

// ---------------------------------------------------------------- shelf
function zoneBar(z) {
  const parts = [["primary", "var(--z-author)"], ["apparatus", "var(--z-apparatus)"], ["front", "var(--z-other)"], ["contents", "var(--z-other)"], ["back", "var(--z-other)"]];
  const tot = Object.values(z).reduce((a, b) => a + (b || 0), 0) || 1;
  return `<div class="zbar">${parts.map(([k, c]) => z[k] ? `<span style="width:${(100 * z[k] / tot).toFixed(2)}%;background:${c}" title="${k}: ${z[k]} words"></span>` : "").join("")}</div>`;
}

function renderShelf() {
  view.innerHTML = `<h1>The pilot shelf</h1>
  <p class="lead">Eight books parsed into ${state.books.reduce((a, b) => a + b.units, 0).toLocaleString()} units with
  ${state.books.reduce((a, b) => a + b.questions, 0).toLocaleString()} generated questions. The bar shows where each book's words sit:
  the author's text, editors' apparatus, and front or back matter. Warnings are parsing defects to fix before lenses run.</p>
  <div class="legend" style="margin-bottom:12px"><span><i style="background:var(--z-author)"></i>primary text</span>
  <span><i style="background:var(--z-apparatus)"></i>apparatus</span><span><i style="background:var(--z-other)"></i>front, contents, back</span>
  <span><i style="background:var(--z-comment)"></i>commentary voice</span></div>
  <div class="shelf">${state.books.map((b) => `
    <div class="card" style="--c:${state.color[b.id]}" data-id="${esc(b.id)}">
      <h3>${esc(b.title)}</h3><div class="id">${esc(b.id)}</div>
      <div class="stats"><span><b>${b.units}</b>units</span><span><b>${b.questions.toLocaleString()}</b>questions</span>
        <span><b>${b.pages}</b>pages</span><span><b>${b.gold}</b>gold</span></div>
      ${zoneBar(b.zones)}
      <div class="small muted">${b.primary_divisions} primary divisions${b.ocr_pages ? ` · ${b.ocr_pages} OCR pages` : ""}
      ${b.commentators.length ? ` · commentators: ${b.commentators.slice(0, 5).map((c) => esc(c[0]) + " " + c[1]).join(", ")}` : ""}</div>
      ${b.warnings.map((w) => `<div class="warn">${esc(w)}</div>`).join("")}
    </div>`).join("")}</div>`;
  view.querySelectorAll(".card").forEach((c) => c.addEventListener("click", () => { location.hash = "#/book/" + encodeURIComponent(c.dataset.id); }));
}

// ---------------------------------------------------------------- book
async function renderBook(eid, unitId, q) {
  view.innerHTML = `<p class="muted">Loading…</p>`;
  const b = await api("/api/book/" + encodeURIComponent(eid));
  const meta = state.books.find((x) => x.id === eid) || {};
  const byDiv = {};
  b.units.forEach((u) => (byDiv[u.div] = byDiv[u.div] || []).push(u));
  const typed = b.units.some((u) => u.type);
  let typeFilter = "";
  view.innerHTML = `<div class="book">
    <div class="col divs"><h1 style="font-size:18px">${esc(meta.title || eid)}</h1>
      ${typed ? `<div class="legend" style="margin:6px 0 4px">${TYPES.map((t) => `<span><i style="background:${TYPE_COLOR[t]}"></i>${t}</span>`).join("")}</div>
      <label class="small">show only <select id="tfilter"><option value="">all types</option>${TYPES.map((t) => `<option>${t}</option>`).join("")}</select></label>`
      : `<div class="legend" style="margin:6px 0 10px"><span><i style="background:var(--z-author)"></i>author</span>
      <span><i style="background:var(--z-comment)"></i>commentary</span><span><i style="background:var(--z-apparatus)"></i>apparatus</span></div>`}
      ${b.divisions.map((d) => {
        const us = byDiv[d.id] || [];
        const words = us.reduce((a, u) => a + u.words, 0) || 1;
        return `<div class="div" data-div="${esc(d.id)}" title="${esc(d.label)}">
          <div class="z">${esc(d.zone)} · p${d.page ?? "?"} · ${us.length} units</div><div class="lab">${esc(d.label)}</div>
          <div class="barcode">${us.map((u) => `<span style="flex:${Math.max(u.words, 8)};background:${unitColor(u, typed)}" title="${esc((u.type ? u.type + " · " : "") + u.ref)}"></span>`).join("")}</div></div>`;
      }).join("")}
      ${b.gold.length ? `<h2>Gold questions (${b.gold.length})</h2>${b.gold.map((g) => `<div class="small" style="margin-bottom:6px">
        <span class="chip">${esc(g.type)}</span><a href="#/ask?q=${encodeURIComponent(g.question)}">${esc(g.question)}</a></div>`).join("")}` : ""}
    </div>
    <div class="col" id="textcol"><div class="text" id="text"><p class="muted">Pick a division on the left.</p></div></div>
    <div class="col side" id="side"><p class="muted">Click a passage to see its questions and its nearest passages in the other books.</p></div>
  </div>`;
  const openDiv = async (divId, selectId) => {
    view.querySelectorAll(".div").forEach((x) => x.classList.toggle("on", x.dataset.div === divId));
    const d = b.divisions.find((x) => x.id === divId);
    const units = await api(`/api/division?book=${encodeURIComponent(eid)}&div=${encodeURIComponent(divId)}`);
    const terms = q ? termsOf(q) : [];
    $("#text").innerHTML = `<div class="divhead">${esc(d.label)} · ${esc(d.zone)}</div>` + units.map((u) => `
      <div class="u ${esc(u.zone)} ${u.voice === "commentary" ? "commentary" : ""}" data-id="${esc(u.id)}">
      <span class="gut">${esc(u.id.split(":").pop())} · p${u.p0}${u.p1 !== u.p0 ? "–" + u.p1 : ""}${u.voice === "commentary" ? " · " + esc(u.voice_name || "commentary") : ""}${u.type ? ` · <b style="color:${TYPE_COLOR[u.type]}">${esc(u.type)}</b>${u.type2 ? " + " + esc(u.type2) : ""}` : ""}</span><div class="ut">${renderUnitText(u, terms)}</div></div>`).join("");
    applyFilter();
    $("#text").querySelectorAll(".u").forEach((el) => el.addEventListener("click", () => selectUnit(el.dataset.id)));
    const target = selectId || (units[0] && units[0].id);
    if (selectId) { const el = $(`.u[data-id="${CSS.escape(selectId)}"]`); if (el) el.scrollIntoView({ block: "center" }); }
    else $("#textcol").scrollTop = 0;
    if (target && selectId) selectUnit(target);
  };
  function applyFilter() {
    $("#text").querySelectorAll(".u").forEach((el) => {
      const u = el.querySelector(".gut b");
      el.style.opacity = !typeFilter || (u && u.textContent === typeFilter) ? 1 : 0.25;
    });
  }
  if (typed) $("#tfilter").addEventListener("change", (e) => { typeFilter = e.target.value; applyFilter(); });
  const selectUnit = async (uid) => {
    $("#text").querySelectorAll(".u").forEach((x) => x.classList.toggle("sel", x.dataset.id === uid));
    const u = await api("/api/unit/" + encodeURIComponent(uid));
    $("#side").innerHTML = `<h3>${esc(u.ref || u.id)}</h3>
      <div class="small muted">${esc(u.id)} · pages ${u.p0}–${u.p1} · ${u.words} words · ${esc(u.zone)} · ${esc(u.voice === "commentary" ? (u.voice_name || "commentary") : "author")}</div>
      <h2>Questions this passage answers</h2><div class="small muted">Generated by the model for retrieval; not the book's words.</div>
      <ul>${u.questions.map((x) => `<li><a class="qlink" href="#/ask?q=${encodeURIComponent(x)}">${esc(x)}</a></li>`).join("") || "<li class='muted'>none</li>"}</ul>
      <h2>Nearest passages in other books</h2>
      ${u.neighbours.map((n) => `<div class="nb" data-ed="${esc(n.edition)}" data-id="${esc(n.id)}">
        <span class="dot" style="--c:${state.color[n.edition]}"></span><b>${esc(short(state.title[n.edition]))}</b>
        <span class="muted">· ${esc(n.ref)} · ${n.sim}</span><div class="sn">${esc(n.snippet)}…</div></div>`).join("") || "<p class='muted'>No vectors for this unit.</p>"}
      <div style="margin-top:10px;display:flex;gap:8px">${u.prev ? `<button data-go="${esc(u.prev)}">← previous</button>` : ""}${u.next ? `<button data-go="${esc(u.next)}">next →</button>` : ""}</div>`;
    $("#side").querySelectorAll(".nb").forEach((el) => el.addEventListener("click", () => {
      location.hash = `#/book/${encodeURIComponent(el.dataset.ed)}?u=${encodeURIComponent(el.dataset.id)}`;
    }));
    $("#side").querySelectorAll("[data-go]").forEach((el) => el.addEventListener("click", () => {
      const nu = b.units.find((x) => x.id === el.dataset.go);
      if (nu) openDiv(nu.div, nu.id);
    }));
  };
  view.querySelectorAll(".div").forEach((el) => el.addEventListener("click", () => openDiv(el.dataset.div)));
  const start = unitId && b.units.find((x) => x.id === unitId);
  if (start) openDiv(start.div, start.id);
  else { const first = b.divisions.find((d) => d.zone === "primary"); if (first) openDiv(first.id); }
}

// the evidence span that pins the passage's type, underlined; query terms highlighted elsewhere
function renderUnitText(u, terms) {
  if (!u.ev) return highlight(u.text, terms);
  const [s, e] = u.ev;
  return highlight(u.text.slice(0, s), terms) + `<span class="ev" title="evidence for '${esc(u.type)}'">` +
    highlight(u.text.slice(s, e), terms) + "</span>" + highlight(u.text.slice(e), terms);
}

function termsOf(q) {
  return norm(q).split(/[^a-z']+/).filter((w) => w.length > 2 && !STOP.has(w));
}
function highlight(text, terms) {
  let s = esc(text);
  if (!terms.length) return s;
  const re = new RegExp("\\b(" + terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")\\w*", "gi");
  return s.replace(re, "<mark>$&</mark>");
}

// ---------------------------------------------------------------- atlas
async function renderAtlas(q) {
  view.innerHTML = `<div class="atlas"><div class="stage"><canvas id="cv"></canvas></div>
    <div class="col side" id="aside"><h1 style="font-size:18px">Atlas of 2,916 passages</h1>
    <p class="small muted">Every unit placed by its meaning (qwen3-embedding vectors, t-SNE). Nearby points say similar things,
    whichever book they come from. Hover to read the reference, click to open the passage. From any answer, “see on the atlas” numbers its results here, which shows whether an answer is one place in one book or scattered across many.</p>
    <div class="toggles" id="tog"></div>
    <label class="small" style="display:block;margin-top:8px"><input type="checkbox" id="onlyPrimary" checked> primary text only</label>
    <div id="apanel" style="margin-top:12px"></div></div></div>`;
  if (!state.atlas) state.atlas = await api("/api/atlas");
  const pts = state.atlas.map(([id, ed, x, y, zone, voice]) => ({ id, ed, x, y, zone, voice }));
  if (!pts.length) { $("#apanel").innerHTML = `<p class="warn">No coordinates yet. Run <code>cli project --db …</code> once.</p>`; return; }
  const hidden = new Set();
  $("#tog").innerHTML = state.books.map((b) => `<label><input type="checkbox" data-ed="${esc(b.id)}" checked>
    <span class="dot" style="--c:${state.color[b.id]}"></span>${esc(short(b.title))}</label>`).join("");
  let hits = [];
  if (q) {
    const r = await api("/api/ask?q=" + encodeURIComponent(q));
    hits = r.hits.map((h) => h.id);
    $("#apanel").innerHTML = `<h2>“${esc(q)}”</h2>` + r.hits.slice(0, 6).map((h, i) => `<div class="nb" data-ed="${esc(h.edition)}" data-id="${esc(h.id)}">
      <span class="dot" style="--c:${state.color[h.edition]}"></span><b>${i + 1}. ${esc(short(state.title[h.edition]))}</b>
      <span class="muted">· ${esc(h.ref)}</span><div class="sn">${esc(h.text.slice(0, 160))}…</div></div>`).join("");
    $("#apanel").querySelectorAll(".nb").forEach((el) => el.addEventListener("click", () => {
      location.hash = `#/book/${encodeURIComponent(el.dataset.ed)}?u=${encodeURIComponent(el.dataset.id)}`; }));
  }
  const cv = $("#cv"), ctx = cv.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  let W = 0, H = 0, pad = 24;
  const X = (x) => pad + x * (W - 2 * pad), Y = (y) => pad + (1 - y) * (H - 2 * pad);
  const visible = (p) => !hidden.has(p.ed) && (!$("#onlyPrimary").checked || p.zone === "primary");
  const draw = (hover) => {
    W = cv.clientWidth; H = cv.clientHeight; cv.width = W * dpr; cv.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    const dim = hits.length > 0;
    for (const p of pts) {
      if (!visible(p)) continue;
      ctx.globalAlpha = dim ? 0.18 : (p.voice === "commentary" ? 0.45 : 0.75);
      ctx.fillStyle = state.color[p.ed];
      ctx.beginPath(); ctx.arc(X(p.x), Y(p.y), p.voice === "commentary" ? 2 : 2.8, 0, 7); ctx.fill();
    }
    ctx.globalAlpha = 1;
    hits.forEach((id, i) => {
      const p = pts.find((t) => t.id === id); if (!p) return;
      ctx.fillStyle = state.color[p.ed]; ctx.strokeStyle = getComputedStyle(document.body).color; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(X(p.x), Y(p.y), i === 0 ? 7 : 5, 0, 7); ctx.fill(); ctx.stroke();
      ctx.fillStyle = getComputedStyle(document.body).color; ctx.font = "600 12px system-ui"; ctx.fillText(String(i + 1), X(p.x) + 8, Y(p.y) - 6);
    });
    if (hover) { ctx.strokeStyle = getComputedStyle(document.body).color; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(X(hover.x), Y(hover.y), 6, 0, 7); ctx.stroke(); }
  };
  const nearest = (mx, my) => {
    let best = null, bd = 100;
    for (const p of pts) { if (!visible(p)) continue; const d = (X(p.x) - mx) ** 2 + (Y(p.y) - my) ** 2; if (d < bd) { bd = d; best = p; } }
    return best;
  };
  cv.addEventListener("mousemove", (e) => {
    const r = cv.getBoundingClientRect(); const p = nearest(e.clientX - r.left, e.clientY - r.top);
    draw(p);
    if (!p) { tip.hidden = true; return; }
    tip.hidden = false; tip.style.left = e.clientX + 14 + "px"; tip.style.top = e.clientY + 10 + "px";
    tip.innerHTML = `<span class="dot" style="--c:${state.color[p.ed]}"></span><b>${esc(short(state.title[p.ed]))}</b><br>${esc(p.id.split(":").pop())} · ${esc(p.zone)}${p.voice === "commentary" ? " · commentary" : ""}`;
  });
  cv.addEventListener("mouseleave", () => { tip.hidden = true; draw(); });
  cv.addEventListener("click", (e) => {
    const r = cv.getBoundingClientRect(); const p = nearest(e.clientX - r.left, e.clientY - r.top);
    if (p) location.hash = `#/book/${encodeURIComponent(p.ed)}?u=${encodeURIComponent(p.id)}`;
  });
  $("#tog").addEventListener("change", (e) => { const ed = e.target.dataset.ed; e.target.checked ? hidden.delete(ed) : hidden.add(ed); draw(); });
  $("#onlyPrimary").addEventListener("change", () => draw());
  window.onresize = () => draw();
  draw();
}

// ---------------------------------------------------------------- ask
async function renderAsk(q) {
  $("#askq").value = q;
  view.innerHTML = `<div class="results"><p class="muted">Routing…</p></div>`;
  const r = await api("/api/ask?q=" + encodeURIComponent(q));
  state.lastAsk = r;
  const anchors = r.gold ? r.gold.gold.map((a) => ({ book: a.book, a: norm(a.anchor) })) : [];
  const isGold = (h) => anchors.some((a) => a.book === h.edition && norm(h.text).includes(a.a));
  const terms = termsOf(q);
  const goldNote = r.gold ? (r.gold.gold.length
      ? (r.hits.some(isGold) ? `<span class="badge ok">gold passage at rank ${r.hits.findIndex(isGold) + 1}</span>` : `<span class="badge">gold passage not in the top ${r.hits.length}</span>`)
      : `<span class="badge">gold: the library should abstain</span>`) : "";
  view.innerHTML = `<div class="results"><h1>${esc(q)}</h1>
    <p class="small muted">${r.mode.join(" + ")} · ${r.ms} ms ${r.notes.length ? "· " + esc(r.notes.join("; ")) : ""} ${r.gold ? `· gold ${esc(r.gold.id)} (${esc(r.gold.type)})` : ""} ${goldNote}
    · <a href="#/atlas?q=${encodeURIComponent(q)}">see on the atlas</a></p>
    ${r.hits.map((h, i) => `<div class="hit ${isGold(h) ? "gold" : ""}" style="--c:${state.color[h.edition]}">
      <div class="meta"><b style="color:var(--ink)">${i + 1}. ${esc(state.title[h.edition] || h.edition)}</b><span>${esc(h.ref)}</span>
        <span>p${h.p0}${h.p1 !== h.p0 ? "–" + h.p1 : ""}</span>${h.zone !== "primary" ? `<span class="chip">${esc(h.zone)}</span>` : ""}
        ${h.voice === "commentary" ? `<span class="chip">${esc(h.voice_name || "commentary")}</span>` : ""}
        <span class="badge" title="rank in the lexical list">bm25 ${h.bm25 ? "#" + h.bm25 : "–"}</span>
        <span class="badge" title="rank in the dense list">dense ${h.dense ? "#" + h.dense : "–"}</span>
        <span class="muted">score ${h.score}</span>${isGold(h) ? `<span class="badge ok">contains gold anchor</span>` : ""}</div>
      <div class="body">${highlight(h.text, terms)}</div>
      <div class="acts"><a href="#/book/${encodeURIComponent(h.edition)}?u=${encodeURIComponent(h.id)}&q=${encodeURIComponent(q)}">open in book</a>
        <button class="small" data-gold="${esc(h.id)}">save as gold</button></div></div>`).join("") || "<p class='muted'>No passages matched.</p>"}</div>`;
  view.querySelectorAll("[data-gold]").forEach((btn) => btn.addEventListener("click", async () => {
    const res = await api("/api/gold", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q, unit_id: btn.dataset.gold }) });
    btn.textContent = `saved (${res.saved} candidates)`; btn.disabled = true;
  }));
}

// ---------------------------------------------------------------- gold
async function renderGold(type) {
  const b = await Promise.all(state.books.map((x) => api("/api/book/" + encodeURIComponent(x.id))));
  const seen = new Set(), items = [];
  b.forEach((bk) => bk.gold.forEach((g) => { if (!seen.has(g.id)) { seen.add(g.id); items.push(g); } }));
  const types = [...new Set(items.map((g) => g.type))].sort();
  const rows = items.filter((g) => !type || g.type === type).sort((a, b) => a.id.localeCompare(b.id));
  view.innerHTML = `<h1>Gold set</h1><p class="lead">The frozen evaluation questions with their gold passages. Click one to see what the router returns and where the gold passage ranks.
    Unanswerable questions have no gold passage and are not listed here.</p>
    <div class="filters"><button class="${!type ? "on" : ""}" data-t="">all ${items.length}</button>${types.map((t) => `<button class="${t === type ? "on" : ""}" data-t="${esc(t)}">${esc(t)} ${items.filter((g) => g.type === t).length}</button>`).join("")}</div>
    <table class="gold"><tr><th>id</th><th>type</th><th>question</th><th>gold</th></tr>
    ${rows.map((g) => `<tr><td>${esc(g.id)}</td><td>${esc(g.type)}</td><td><a href="#/ask?q=${encodeURIComponent(g.question)}">${esc(g.question)}</a></td>
      <td class="small">${g.gold.map((a) => `<span class="dot" style="--c:${state.color[a.book]}"></span>${esc(short(state.title[a.book] || a.book))} p${a.page}`).join("<br>")}</td></tr>`).join("")}</table>`;
  view.querySelectorAll("[data-t]").forEach((x) => x.addEventListener("click", () => { location.hash = "#/gold" + (x.dataset.t ? "?type=" + encodeURIComponent(x.dataset.t) : ""); }));
}

init().catch((e) => { view.innerHTML = `<p class="warn">${esc(e.message)}</p>`; });
