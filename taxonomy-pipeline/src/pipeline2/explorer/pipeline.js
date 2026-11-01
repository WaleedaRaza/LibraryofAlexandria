// LibXNDR explorer: #/pipeline, live status of the current run. Polls while the page is open.
let pipeTimer = null;

function stopPipeline() { clearTimeout(pipeTimer); pipeTimer = null; }

function hms(s) {
  if (s == null) return "";
  const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m`;
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
      <section class="col"><h2>Steps</h2>${r.steps.length ? `<ol class="steps">${r.steps.map(renderStep).join("")}</ol>`
        : `<p class="muted">No data/pipeline.json yet.</p>`}</section>
      <div class="pipeside">
        <section class="col"><h2>Running now</h2>${r.jobs.length ? r.jobs.map((j) => `<div class="small mono">${esc(j.pid)} ${esc(j.cmd)}</div>`).join("") : `<p class="muted">Nothing.</p>`}
          <div class="small muted">Models loaded: ${esc(sv.models.join(", ") || "none")}</div></section>
        ${r.dbs.map(renderDb).join("")}
      </div>
    </div>
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
    view.innerHTML = pipelineHtml(r);
    if (log) $(".pipelog").scrollTop = top;
  } catch (e) {
    if (location.hash !== here) return;
    view.innerHTML = `<p class="warn">Could not read pipeline status: ${esc(e.message)}. Retrying.</p>`;
  }
  pipeTimer = setTimeout(renderPipeline, 5000);
}
