// LibXNDR explorer: #/pipeline, live status of the current run. Polls while the page is open.
let pipeTimer = null;

function stopPipeline() { clearTimeout(pipeTimer); pipeTimer = null; }

function hms(s) {
  if (s == null) return "";
  const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m`;
}

function spark(points, w = 220, h = 36, max = null) {
  if (!points || points.length < 2) return `<svg class="spark" width="${w}" height="${h}"></svg>`;
  const top = max ?? Math.max(1, ...points);
  const step = w / (points.length - 1);
  const d = points.map((v, i) => `${(i * step).toFixed(1)},${(h - 2 - (h - 4) * Math.min(v, top) / top).toFixed(1)}`).join(" ");
  return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><polyline points="${d}" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>`;
}

function renderGpu(g, hist) {
  if (!g) return `<section class="col"><h2>GPU</h2><p class="muted">nvidia-smi not available.</p></section>`;
  const util = hist.map((r) => r[1]), mem = hist.map((r) => r[2] / 1024);
  const span = hist.length > 1 ? hms(hist[hist.length - 1][0] - hist[0][0]) : "";
  return `<section class="col gpu"><h2>${esc(g.name || "GPU")} <span class="muted">${span ? `last ${span}` : ""}</span></h2>
    <div class="gpurow"><div class="gpustat"><b>${g.util}%</b>load</div>${spark(util, 220, 36, 100)}</div>
    <div class="gpurow"><div class="gpustat"><b>${(g.used_mb / 1024).toFixed(1)}</b>of ${(g.total_mb / 1024).toFixed(0)} GB</div>${spark(mem, 220, 36, g.total_mb / 1024)}</div>
    <div class="stats wrap">
      ${g.temp_c != null ? `<div><b>${g.temp_c}°C</b>temp</div>` : ""}
      ${g.power_w != null ? `<div><b>${Math.round(g.power_w)} W</b>${g.power_limit_w ? `of ${Math.round(g.power_limit_w)}` : "power"}</div>` : ""}
      ${g.fan_pct != null ? `<div><b>${g.fan_pct}%</b>fan</div>` : ""}
      ${g.clock_mhz != null ? `<div><b>${g.clock_mhz}</b>MHz</div>` : ""}
    </div></section>`;
}

function renderLoaded(sv) {
  if (!sv.loaded || !sv.loaded.length) return `<div class="small muted">No model loaded in VRAM.</div>`;
  return sv.loaded.map((m) => `<div class="small"><b>${esc(m.name)}</b> ${m.vram_gb} GB in VRAM${m.ctx ? `, ${m.ctx.toLocaleString()} ctx` : ""}${m.expires ? `, <span class="muted">unloads ${esc(m.expires.slice(11))}</span>` : ""}</div>`).join("");
}

function renderNow(r) {
  const lv = (r.live || []).filter((j) => j.fresh && !j.done);
  const a = r.activity;
  let head = "";
  if (lv.length) {
    head = lv.map((j) => `<div class="now live"><div class="small"><span class="pulse"></span><b>${esc(j.job)}</b> · ${esc(j.model || "")}${j.workers > 1 ? ` · ${j.workers} workers` : ""}
        ${j.total ? ` · ${Number(j.n).toLocaleString()} / ${Number(j.total).toLocaleString()}` : ""} <span class="muted">${j.age_s}s ago</span></div>
      ${j.book ? `<div><b>${esc(j.book)}</b> <span class="muted">${esc(j.ref || "")}</span></div>` : ""}
      ${j.text ? `<div class="snippet">${esc(j.text)}…</div>` : ""}</div>`).join("");
  } else if (a && a.recent.length) {
    const x = a.recent[0];
    head = `<div class="now"><div class="small muted">Last committed label, ${hms(x.age_s) || "<1m"} ago (the typing job commits every 50 passages; live heartbeat comes with the next run)</div>
      <div><b>${esc(x.book)}</b> <span class="muted">${esc(x.ref)}</span> → <span class="chip">${esc(x.type)}</span></div>
      <div class="snippet">“${esc(x.quote)}”</div></div>`;
  } else {
    head = `<p class="muted">Nothing being parsed.</p>`;
  }
  const feed = a ? `<div class="small muted" style="margin-top:8px">${a.per_10min} labels in the last 10 min · ${esc(a.db)}</div>
    <table class="pipe feed"><tbody>${a.recent.slice(0, 8).map((x) => `<tr><td class="muted">${hms(x.age_s) || "<1m"}</td><td>${esc((x.book || "").slice(0, 28))}</td><td class="muted">${esc((x.ref || "").slice(0, 22))}</td><td><span class="chip">${esc(x.type)}</span>${x.pinned ? "" : " <span class='muted'>unpinned</span>"}</td></tr>`).join("")}</tbody></table>` : "";
  const books = a ? `<h2>Coverage by book</h2><div class="cov">${a.books.map((b) => { const pct = b.units ? Math.round(100 * b.typed / b.units) : 0;
      return `<div class="covrow" title="${esc(b.book)}: ${b.typed}/${b.units}"><span class="covname">${esc((b.book || "").slice(0, 34))}</span><span class="pbar"><i style="width:${pct}%"></i></span><span class="covpct">${pct}%</span></div>`; }).join("")}</div>` : "";
  return `<section class="col"><h2>Parsing now</h2>${head}${feed}${books}</section>`;
}

let cfgDirty = false;
function renderConfig(r) {
  const names = new Set((r.installed || []).map((m) => m.name));
  Object.values(r.config).forEach((c) => names.add(c.model));
  const opts = (sel) => [...names].sort().map((n) => `<option ${n === sel ? "selected" : ""}>${esc(n)}</option>`).join("");
  const inst = (r.installed || []).map((m) => `<span class="chip" title="${esc(m.family || "")} ${esc(m.quant || "")}">${esc(m.name)} <span class="muted">${m.gb} GB</span></span>`).join(" ");
  const pulls = (r.pulls || []).map((p) => `<div class="small"><b>${esc(p.name)}</b> ${esc(p.state)} ${p.state === "pulling" ? `${p.pct}%` : ""} <span class="muted">${esc(p.status)}</span>
      ${p.state === "pulling" ? `<div class="pbar"><i style="width:${p.pct}%"></i></div>` : ""}</div>`).join("");
  const benches = (r.benches || []).map((b) => { const n = b.done || 0, agree = n ? Math.round(100 * b.agree / n) : 0;
    return `<tr><td>${esc(b.model)}</td><td>${esc(b.state)}${b.state === "waiting" ? " <span class='muted'>(GPU busy)</span>" : ""}</td><td>${n}/${b.n}</td><td>${n ? agree + "%" : ""}</td><td>${n ? Math.round(100 * b.pinned / n) + "%" : ""}</td><td>${n && b.secs ? (b.secs / n).toFixed(1) + " s" : ""}</td></tr>`; }).join("");
  return `<section class="col cfg"><h2>Models and workers <span class="muted">next run</span></h2>
    <table class="pipe cfgtab"><thead><tr><th>Stage</th><th>Model</th><th>Workers</th></tr></thead><tbody>
    ${Object.entries(r.config).map(([k, c]) => `<tr><td><b>${esc(k)}</b><div class="small muted">${esc(c.what)}</div></td>
      <td><select data-stage="${esc(k)}" data-f="model">${opts(c.model)}</select></td>
      <td><input type="number" min="1" max="8" value="${c.workers}" data-stage="${esc(k)}" data-f="workers"></td></tr>`).join("")}
    </tbody></table>
    <div class="cfgbar"><button id="cfgsave">Save config</button><span class="small muted" id="cfgmsg">Saved to data/pipeline_config.json; label.py and edges.py read it when --model/--workers are not given. Workers above 1 need OLLAMA_NUM_PARALLEL.</span></div>
    <h2>Installed models</h2><div class="chips">${inst || "<span class='muted'>Ollama not reachable.</span>"}</div>
    <div class="cfgbar"><input id="pullname" placeholder="qwen3.5:4b" list="pullhints"><datalist id="pullhints"><option value="qwen3.5:4b"><option value="qwen3.5:9b"><option value="gemma4:12b"><option value="qwen3-embedding:4b"></datalist>
      <button id="pullbtn">Pull</button><span class="small muted">Download only, no GPU use; safe while a job runs.</span></div>${pulls}
    <h2>Bench a model on typing</h2>
    <div class="cfgbar"><select id="benchmodel">${opts("")}</select><button id="benchbtn">Bench 30 passages</button><label class="small"><input type="checkbox" id="benchforce"> run now even if the GPU is busy</label>
      <span class="small muted">Re-types 30 already-labelled passages and reports agreement with the stored labels, pinned rate and seconds per passage. Waits until the GPU is free.</span></div>
    ${benches ? `<table class="pipe"><thead><tr><th>Model</th><th>State</th><th>Done</th><th>Agree</th><th>Pinned</th><th>Per passage</th></tr></thead><tbody>${benches}</tbody></table>` : ""}
  </section>`;
}

function wireConfig() {
  const cfg = $(".cfg");
  if (!cfg) return;
  cfg.addEventListener("input", () => { cfgDirty = true; });
  $("#cfgsave", cfg).onclick = async () => {
    const body = {};
    cfg.querySelectorAll("[data-stage]").forEach((el) => { (body[el.dataset.stage] ??= {})[el.dataset.f] = el.value; });
    const res = await fetch("/api/pipeline/config", { method: "POST", body: JSON.stringify(body) });
    $("#cfgmsg", cfg).textContent = res.ok ? "Saved." : "Save failed.";
    cfgDirty = false;
  };
  $("#pullbtn", cfg).onclick = async () => {
    const model = $("#pullname", cfg).value.trim();
    if (model) { await fetch("/api/pipeline/pull", { method: "POST", body: JSON.stringify({ model }) }); cfgDirty = false; renderPipeline(); }
  };
  $("#benchbtn", cfg).onclick = async () => {
    await fetch("/api/pipeline/bench", { method: "POST", body: JSON.stringify({ model: $("#benchmodel", cfg).value, n: 30, force: $("#benchforce", cfg).checked }) });
    cfgDirty = false; renderPipeline();
  };
}

function renderStep(s) {
  const p = s.progress;
  const pct = p ? Math.round(100 * p.n / p.total) : 0;
  const when = s.state === "done" ? `done ${esc(s.at)}` : s.state === "failed" ? `failed, exit ${esc(s.exit)}, ${esc(s.at)}` : s.state;
  return `<li class="step ${esc(s.state)}"><div class="stephead"><b>${esc(s.n)}. ${esc(s.name)}</b><span class="stepstate">${when}</span></div>
    ${s.detail ? `<div class="small muted">${esc(s.detail)}</div>` : ""}
    ${p ? `<div class="pbar" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"><i style="width:${pct}%"></i></div>
      <div class="small">${p.n.toLocaleString()} / ${p.total.toLocaleString()} (${pct}%)${p.each ? `, ${p.each}s each, about ${hms(p.eta_s)} left` : ""}</div>`
      : s.tail ? `<div class="small muted mono">${esc(s.tail)}</div>` : ""}
    ${s.outputs.length ? `<div class="small muted">${s.outputs.map((o) => `${o.exists ? "✓" : "·"} ${esc(o.path)}`).join("<br>")}</div>` : ""}</li>`;
}

function renderCounts(obj) {
  return Object.entries(obj).map(([k, v]) => `<div><b>${Number(v).toLocaleString()}</b>${esc(k)}</div>`).join("");
}

function renderDb(d) {
  return `<section class="col"><h2>${esc(d.name)}</h2><div class="stats wrap">${renderCounts(d.tables)}</div>
    ${d.error ? `<p class="warn">${esc(d.error)}</p>` : ""}
    ${d.types ? `<h2>Passage types</h2><div class="stats wrap">${renderCounts(d.types)}</div>` : ""}
    ${d.edges ? `<h2>Graph edges</h2><div class="stats wrap">${renderCounts(d.edges)}</div>` : ""}</section>`;
}

function renderScore(s) {
  const best = Math.max(...s.variants.map((v) => v.first)), bestTop = Math.max(...s.variants.map((v) => v.top10));
  return `<section class="col"><h2>${esc(s.file)} <span class="muted">${esc(s.n)} questions</span></h2>
    <table class="pipe"><thead><tr><th>Variant</th><th>Ranked first</th><th>Top 10</th></tr></thead><tbody>
    ${s.variants.map((v) => `<tr><td>${esc(v.name)}</td><td class="${v.first === best ? "top" : ""}">${v.first}</td><td class="${v.top10 === bestTop ? "top" : ""}">${v.top10}</td></tr>`).join("")}
    </tbody></table></section>`;
}

function pipelineHtml(r) {
  const g = r.gpu, sv = r.services;
  return `<div class="pipehead"><div><h1>${esc(r.name) || "Pipeline"}</h1>
      <p class="lead">Updated ${esc(r.time)}. Refreshes every 5 seconds.</p></div>
      <div class="stats wrap">
        <div><b>${r.queue_alive ? "Running" : "Stopped"}</b>queue</div>
        <div><b>${g ? g.util + "%" : "n/a"}</b>GPU load</div>
        <div><b>${g ? (g.used_mb / 1024).toFixed(1) + " / " + (g.total_mb / 1024).toFixed(0) + " GB" : "n/a"}</b>GPU memory</div>
        <div><b>${sv.ollama ? "Up" : "Down"}</b>Ollama</div>
        <div><b>${sv.reranker ? "Up" : "Down"}</b>reranker</div>
      </div></div>
    <div class="pipegrid">
      <div class="pipeside">
        <section class="col"><h2>Steps</h2>${r.steps.length ? `<ol class="steps">${r.steps.map(renderStep).join("")}</ol>`
          : `<p class="muted">No data/pipeline.json yet.</p>`}</section>
        ${renderNow(r)}
      </div>
      <div class="pipeside">
        ${renderGpu(g, r.gpu_history || [])}
        <section class="col"><h2>Running now</h2>${r.jobs.length ? r.jobs.map((j) => `<div class="small mono">${esc(j.pid)} ${esc(j.cmd)}</div>`).join("") : `<p class="muted">Nothing.</p>`}
          <div style="margin-top:6px">${renderLoaded(sv)}</div></section>
        ${r.dbs.map(renderDb).join("")}
      </div>
    </div>
    ${renderConfig(r)}
    <h2>Search scores</h2><div class="shelf">${r.scores.map(renderScore).join("") || `<p class="muted">No results yet.</p>`}</div>
    <h2>Queue log</h2><pre class="pipelog">${esc(r.log.join("\n")) || "Empty."}</pre>`;
}

async function renderPipeline() {
  stopPipeline();
  const here = location.hash;
  if (!$(".pipehead")) view.innerHTML = `<p class="muted">Loading…</p>`;
  try {
    const r = await api("/api/pipeline");
    if (location.hash !== here) return;
    const log = $(".pipelog"), top = log ? log.scrollTop : 0;
    const oldCfg = $(".cfg"), keep = oldCfg && (cfgDirty || oldCfg.matches(":focus-within"));
    view.innerHTML = pipelineHtml(r);
    if (keep) $(".cfg").replaceWith(oldCfg); else wireConfig();
    if (log) $(".pipelog").scrollTop = top;
  } catch (e) {
    if (location.hash !== here) return;
    view.innerHTML = `<p class="warn">Could not read pipeline status: ${esc(e.message)}. Retrying.</p>`;
  }
  pipeTimer = setTimeout(renderPipeline, 5000);
}
