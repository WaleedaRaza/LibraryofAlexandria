"""Shared state between pipeline jobs and the dashboard: heartbeats, run config, model pulls, benches.

Heartbeats: a job calls `beat(db, "types", unit=..., book=..., ref=..., n=..., total=...)` once per item; it writes
data/live/<job>.json atomically, so the dashboard can show what is being parsed right now. Files older than
`STALE` seconds are ignored.

Run config: data/pipeline_config.json holds the model and worker count per stage. Jobs read it through `model_for`
and `workers_for` when their --model/--workers flags are not given, so the dashboard's form changes the next run.
"""
from __future__ import annotations
import json
import os
import re
import sqlite3
import threading
import time
import urllib.request
from pathlib import Path

STALE = 90
STAGES = ["questions", "vectors", "types", "claims", "edges", "need", "judge"]
DEFAULTS = {
    "questions": {"model": "gemma4:12b", "workers": 1, "what": "S7: questions a reader might bring to each passage"},
    "vectors": {"model": "qwen3-embedding:4b", "workers": 1, "what": "S8: passage and question embeddings"},
    "types": {"model": "gemma4:12b", "workers": 1, "what": "Passage type, pinned to a quote (label.py)"},
    "claims": {"model": "gemma4:12b", "workers": 1, "what": "1–3 claims per typed passage (edges.py claims)"},
    "edges": {"model": "gemma4:12b", "workers": 1, "what": "Relation between two claims (edges.py judge)"},
    "need": {"model": "gemma4:12b", "workers": 1, "what": "What kind of answer a question wants (query_stage plan)"},
    "judge": {"model": "gemma4:12b", "workers": 1, "what": "Listwise judge over the top ten (query_stage --judge)"},
}
_lock = threading.Lock()


def data_dir(db: str | os.PathLike) -> Path:
    return Path(db).resolve().parent


# ---------------------------------------------------------------- heartbeats
def beat(db, job: str, **fields) -> None:
    d = data_dir(db) / "live"
    try:
        d.mkdir(exist_ok=True)
        tmp = d / f"{job}.json.tmp"
        tmp.write_text(json.dumps({"job": job, "time": time.time(), "pid": os.getpid(), **fields}, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, d / f"{job}.json")
    except OSError:
        pass


def live_jobs(db) -> list[dict]:
    d = data_dir(db) / "live"
    out = []
    if not d.exists():
        return out
    now = time.time()
    for f in d.glob("*.json"):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        j["age_s"] = round(now - j.get("time", 0))
        j["fresh"] = j["age_s"] < STALE
        out.append(j)
    return sorted(out, key=lambda j: j["age_s"])


# ---------------------------------------------------------------- run config
def config_path(db) -> Path:
    return data_dir(db) / "pipeline_config.json"


def load_config(db) -> dict:
    cfg = {k: dict(v) for k, v in DEFAULTS.items()}
    p = config_path(db)
    if p.exists():
        try:
            for k, v in json.loads(p.read_text(encoding="utf-8")).items():
                if k in cfg and isinstance(v, dict):
                    cfg[k].update({kk: v[kk] for kk in ("model", "workers") if kk in v})
        except (OSError, ValueError):
            pass
    return cfg


def save_config(db, body: dict) -> dict:
    cfg = load_config(db)
    for k, v in (body or {}).items():
        if k in cfg and isinstance(v, dict):
            if v.get("model"):
                cfg[k]["model"] = str(v["model"])[:80]
            if "workers" in v:
                cfg[k]["workers"] = max(1, min(8, int(v["workers"] or 1)))
    config_path(db).write_text(json.dumps({k: {"model": v["model"], "workers": v["workers"]} for k, v in cfg.items()}, indent=1), encoding="utf-8")
    return cfg


def model_for(db, stage: str, given: str | None = None) -> str:
    return given or load_config(db)[stage]["model"]


def workers_for(db, stage: str, given: int | None = None) -> int:
    return given or int(load_config(db)[stage]["workers"])


# ---------------------------------------------------------------- Ollama: installed models, pulls
def _req(url, body=None, timeout=5):
    req = urllib.request.Request(url, json.dumps(body).encode() if body is not None else None,
                                 {"Content-Type": "application/json"} if body is not None else {})
    return urllib.request.urlopen(req, timeout=timeout)


def installed(ollama="http://localhost:11434") -> list[dict]:
    try:
        with _req(f"{ollama}/api/tags") as r:
            tags = json.loads(r.read()).get("models", [])
    except Exception:
        return []
    return [{"name": m["name"], "gb": round(m.get("size", 0) / 1e9, 1), "family": (m.get("details") or {}).get("family"),
             "params": (m.get("details") or {}).get("parameter_size"), "quant": (m.get("details") or {}).get("quantization_level")}
            for m in sorted(tags, key=lambda m: m["name"])]


_pulls: dict[str, dict] = {}


def pull(name: str, ollama="http://localhost:11434") -> dict:
    """Start downloading a model in the background (network and disk only; no GPU). Progress via `pulls()`."""
    name = name.strip()
    if not re.fullmatch(r"[\w.\-/:]+", name):
        return {"error": "bad model name"}
    with _lock:
        if name in _pulls and _pulls[name].get("state") == "pulling":
            return _pulls[name]
        _pulls[name] = {"name": name, "state": "pulling", "pct": 0, "status": "starting", "started": time.time()}

    def go():
        try:
            with _req(f"{ollama}/api/pull", {"model": name, "stream": True}, timeout=24 * 3600) as r:
                for line in r:
                    j = json.loads(line)
                    st = _pulls[name]
                    st["status"] = j.get("status", "")
                    if j.get("total"):
                        st["pct"] = round(100 * j.get("completed", 0) / j["total"], 1)
                    if j.get("error"):
                        st.update(state="failed", status=j["error"])
                        return
            _pulls[name].update(state="done", pct=100, status="pulled")
        except Exception as e:
            _pulls[name].update(state="failed", status=str(e)[:200])

    threading.Thread(target=go, daemon=True).start()
    return _pulls[name]


def pulls() -> list[dict]:
    return sorted(_pulls.values(), key=lambda p: -p["started"])


# ---------------------------------------------------------------- bench: a candidate model against the labels we have
_bench: dict[str, dict] = {}


def bench(db: str, model: str, n: int = 30, ollama="http://localhost:11434", busy=lambda: False, force: bool = False) -> dict:
    """Type `n` already-labelled passages with `model` and compare with the stored labels. Waits while `busy()`
    (another GPU job running) so it never contends for the card; writes analysis/bench_<model>.json."""
    from .label import SYSTEM, SCHEMA, _anchor
    key = model
    with _lock:
        if key in _bench and _bench[key]["state"] in ("waiting", "running"):
            return _bench[key]
        _bench[key] = {"model": model, "n": n, "state": "waiting", "done": 0, "agree": 0, "pinned": 0, "secs": 0.0,
                       "started": time.time(), "rows": [], "force": force}
    st = _bench[key]

    def go():
        waited = 0
        while not force and busy() and waited < 24 * 3600:
            st["state"] = "waiting"
            time.sleep(20)
            waited += 20
        st["state"] = "running"
        con = sqlite3.connect(f"file:{Path(db).as_posix()}?mode=ro", uri=True, timeout=5)
        try:
            rows = con.execute(
                "SELECT u.id, u.text, u.ref, json_extract(e.data,'$.detected_title'), l.type FROM unit_label l JOIN unit u ON u.id=l.unit_id "
                "JOIN edition e ON e.id=u.edition_id WHERE l.model!='rule' AND u.zone='primary' ORDER BY random() LIMIT ?", (n,)).fetchall()
        finally:
            con.close()
        for uid, text, ref, title, gold in rows:
            user = f"Book: {title}\nLocation: {ref}\n\nPassage:\n{text[:3500]}"
            body = {"model": model, "stream": False, "think": False, "format": SCHEMA, "options": {"temperature": 0},
                    "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]}
            t0 = time.time()
            try:
                with _req(f"{ollama}/api/chat", body, timeout=600) as r:
                    out = json.loads(json.loads(r.read())["message"]["content"])
            except Exception as e:
                st["rows"].append({"unit": uid, "ref": ref, "have": gold, "got": None, "error": str(e)[:120]})
                st["done"] += 1
                continue
            s, _ = _anchor(text, out.get("evidence", ""))
            st["secs"] += time.time() - t0
            st["done"] += 1
            st["agree"] += out.get("type") == gold
            st["pinned"] += s >= 0
            st["rows"].append({"unit": uid, "ref": ref, "have": gold, "got": out.get("type"), "pinned": s >= 0,
                               "quote": (out.get("evidence") or "")[:120]})
        st["state"] = "done"
        st["finished"] = time.time()
        try:
            out_dir = data_dir(db).parent / "analysis"
            out_dir.mkdir(exist_ok=True)
            (out_dir / f"bench_{re.sub(r'[^\w.-]', '_', model)}.json").write_text(json.dumps(st, indent=1, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    threading.Thread(target=go, daemon=True).start()
    return st


def benches(db) -> list[dict]:
    """Live benches plus finished ones from analysis/bench_*.json (summary only)."""
    seen, out = set(), []
    for b in _bench.values():
        seen.add(b["model"])
        out.append({k: v for k, v in b.items() if k != "rows"} | {"rows": b["rows"][-8:]})
    d = data_dir(db).parent / "analysis"
    if d.exists():
        for f in sorted(d.glob("bench_*.json"), key=lambda f: -f.stat().st_mtime):
            try:
                b = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if b.get("model") not in seen:
                out.append({k: v for k, v in b.items() if k != "rows"} | {"rows": b.get("rows", [])[-8:], "file": f.name})
    return out
