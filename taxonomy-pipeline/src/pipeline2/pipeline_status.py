"""Live state for the explorer's #/pipeline page. Read-only: logs, databases, processes, GPU.

Steps come from data/pipeline.json (edit it for the next run):
  {"name": "...", "steps": [{"n": 0, "name": "...", "detail": "...", "log": "label.log", "outputs": ["analysis/x.json"]}]}
A queue script reports each step in data/queue.log as `=== STEP n done, exit X, HH:MM`; only lines after
the last `=== queue started` count, so a new run starts clean in the same log.
"""
from __future__ import annotations
import collections
import json
import os
import re
import sqlite3
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

from . import live

JOBS = r"queue\.ps1|query_stage|pipeline2\.(label|edges|cli|carry)"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
SHADOW = ("_data", "_idx", "_content", "_docsize", "_config")
PROCS_TTL = 5.0
_procs = (0.0, [])
_lock = threading.Lock()
_scores = {}


def read_log(path: Path, tail: int = 40) -> list[str]:
    """Last lines of a log; Tee-Object in Windows PowerShell 5.1 writes UTF-16."""
    if not path.exists():
        return []
    raw = path.read_bytes()
    text = raw.decode("utf-16", "replace") if raw[:2] == b"\xff\xfe" else raw.decode("utf-8", "replace")
    return [l for l in text.splitlines() if l.strip()][-tail:]


def processes() -> list[dict]:
    global _procs
    with _lock:
        if time.time() - _procs[0] < PROCS_TTL:
            return _procs[1]
        ps = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match '" + JOBS + "' -and "
              "$_.Name -ne 'cmd.exe' -and $_.CommandLine -notmatch 'Get-CimInstance' } | "
              "Select-Object ProcessId,ParentProcessId,CommandLine | ConvertTo-Json -Compress")
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                                 timeout=15, creationflags=NO_WINDOW).stdout.strip()
            rows = json.loads(out) if out else []
            rows = [rows] if isinstance(rows, dict) else rows
        except Exception:
            rows = []
        pids = {r["ProcessId"] for r in rows}
        jobs = [{"pid": r["ProcessId"], "cmd": _short(r["CommandLine"])} for r in rows if r["ParentProcessId"] not in pids]
        _procs = (time.time(), jobs)
        return jobs


def _short(cmd: str) -> str:
    m = re.search(r"(query_stage\.py.*|-m src\.pipeline2\..*|queue\.ps1)", cmd or "")
    return (m.group(1) if m else cmd or "").replace("src.pipeline2.", "")[:160]


GPU_FIELDS = "memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw,power.limit,fan.speed,clocks.sm,name"
_hist: collections.deque = collections.deque(maxlen=240)      # one sample every 3 s: 12 minutes
_sampler_on = False


def gpu() -> dict | None:
    try:
        out = subprocess.run(["nvidia-smi", f"--query-gpu={GPU_FIELDS}", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5, creationflags=NO_WINDOW).stdout
        f = [x.strip() for x in out.strip().splitlines()[0].split(",")]
        num = lambda x: None if x in ("", "[N/A]", "N/A") else float(x)
        return {"used_mb": int(num(f[0])), "total_mb": int(num(f[1])), "util": int(num(f[2])), "temp_c": num(f[3]),
                "power_w": num(f[4]), "power_limit_w": num(f[5]), "fan_pct": num(f[6]), "clock_mhz": num(f[7]), "name": f[8]}
    except Exception:
        return None


def _sample():
    while True:
        g = gpu()
        if g:
            _hist.append((round(time.time()), g["util"], g["used_mb"], g["temp_c"], g["power_w"]))
        time.sleep(3)


def gpu_history() -> list:
    global _sampler_on
    if not _sampler_on:
        _sampler_on = True
        threading.Thread(target=_sample, daemon=True).start()
    return list(_hist)


def _get(url: str):
    try:
        with urllib.request.urlopen(url, timeout=1.5) as r:
            return json.loads(r.read())
    except Exception:
        return None


def services() -> dict:
    ps = _get("http://localhost:11434/api/ps")
    models = [{"name": m["name"], "vram_gb": round((m.get("size_vram") or 0) / 1e9, 1), "size_gb": round((m.get("size") or 0) / 1e9, 1),
               "ctx": m.get("context_length"), "expires": m.get("expires_at", "")[:19].replace("T", " ")} for m in (ps or {}).get("models", [])]
    return {"ollama": ps is not None, "models": [m["name"] for m in models], "loaded": models,
            "reranker": _get("http://127.0.0.1:8088/health") is not None}


def activity(path: Path) -> dict | None:
    """What the typing job has written lately: the last committed labels and per-book coverage."""
    if not path.exists():
        return None
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=2)
    try:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE name='unit_label'").fetchone():
            return None
        recent = [{"unit": u, "book": b, "ref": r, "type": t, "quote": (q or "")[:140], "pinned": st >= 0, "age_s": round(time.time() - c)}
                  for u, b, r, t, q, st, c in con.execute(
                      "SELECT l.unit_id, json_extract(e.data,'$.detected_title'), u.ref, l.type, l.quote, l.start, l.created FROM unit_label l "
                      "JOIN unit u ON u.id=l.unit_id JOIN edition e ON e.id=u.edition_id WHERE l.model!='rule' ORDER BY l.created DESC LIMIT 8")]
        books = [{"book": b, "units": n, "typed": d or 0} for b, n, d in con.execute(
            "SELECT json_extract(e.data,'$.detected_title'), count(*), sum(l.unit_id IS NOT NULL) FROM unit u JOIN edition e ON e.id=u.edition_id "
            "LEFT JOIN unit_label l ON l.unit_id=u.id GROUP BY u.edition_id ORDER BY e.id")]
        rate = con.execute("SELECT count(*) FROM unit_label WHERE model!='rule' AND created > ?", (time.time() - 600,)).fetchone()[0]
        return {"db": path.name, "recent": recent, "books": books, "per_10min": rate}
    except sqlite3.Error:
        return None
    finally:
        con.close()


def db_stats(path: Path) -> dict | None:
    if not path.exists():
        return None
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=2)
    try:
        names = [n for n, s in con.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
                 if not n.startswith("sqlite_") and not n.endswith(SHADOW) and "VIRTUAL" not in (s or "")]
        out = {"name": path.name, "tables": {n: con.execute(f'SELECT count(*) FROM "{n}"').fetchone()[0] for n in names}}
        if "unit_label" in names:
            out["types"] = dict(con.execute("SELECT type, count(*) FROM unit_label GROUP BY 1 ORDER BY 2 DESC").fetchall())
        if "claim_pair" in names:
            out["edges"] = dict(con.execute("SELECT coalesce(rel, 'unjudged'), count(*) FROM claim_pair GROUP BY 1 ORDER BY 2 DESC").fetchall())
        return out
    except sqlite3.Error as e:
        return {"name": path.name, "error": str(e), "tables": {}}
    finally:
        con.close()


def scores(analysis: Path) -> list[dict]:
    """Every eval result in analysis/: ranked first and top 10 per variant, newest first."""
    out = []
    for f in sorted(analysis.glob("*.json"), key=lambda x: -x.stat().st_mtime):
        key = (f.name, f.stat().st_mtime)
        if key not in _scores:
            try:
                rows = json.loads(f.read_text(encoding="utf-8"))
                ok = isinstance(rows, list) and rows and isinstance(rows[0], dict) and "ranks" in rows[0]
            except (ValueError, OSError):
                ok = False
            _scores[key] = None
            if ok:
                ranks = {k: [r["ranks"].get(k) for r in rows] for k in rows[0]["ranks"]}
                _scores[key] = {"file": f.name, "n": len(rows), "variants": [
                    {"name": k, "first": sum(y == 1 for y in v), "top10": sum(1 for y in v if y and y <= 10)}
                    for k, v in ranks.items()]}
        if _scores[key]:
            out.append(_scores[key])
    return out


def progress(lines: list[str]) -> dict | None:
    """Latest `n/total` in a log, with `Xs each` when the line has it."""
    for l in reversed(lines):
        m = re.search(r"(\d+)/(\d+)", l)
        if m and int(m.group(2)) > 0:
            each = re.search(r"([\d.]+)s each", l)
            n, total, s = int(m.group(1)), int(m.group(2)), float(each.group(1)) if each else None
            return {"n": n, "total": total, "each": s, "eta_s": (total - n) * s if s else None, "line": l.strip()}
    return None


def steps(data: Path, root: Path, alive: bool, log: list[str]) -> tuple[str, list[dict]]:
    f = data / "pipeline.json"
    if not f.exists():
        return "", []
    plan = json.loads(f.read_text(encoding="utf-8"))
    last = max((i for i, l in enumerate(log) if l.startswith("=== queue started")), default=-1)
    done = {}
    for l in log[last + 1:]:
        m = re.match(r"=== STEP (\d+) done, exit (-?\d+), (\S+)", l)
        if m:
            done[int(m.group(1))] = (int(m.group(2)), m.group(3))
    out, running = [], False
    for s in plan["steps"]:
        row = dict(s, outputs=[{"path": o, "exists": (root / o).exists()} for o in s.get("outputs", [])])
        if s["n"] in done:
            code, at = done[s["n"]]
            row.update(state="failed" if code else "done", exit=code, at=at)
        elif alive and not running:
            running = True
            row["state"] = "running"
            lines = read_log(data / s["log"]) if s.get("log") else log[-20:]
            row["progress"] = progress(lines)
            row["tail"] = lines[-1] if lines else ""
        else:
            row["state"] = "stalled" if not alive and last >= 0 else "pending"
        out.append(row)
    return plan.get("name", ""), out


def status(db_path: str) -> dict:
    data = Path(db_path).resolve().parent
    root = data.parent
    jobs = processes()
    alive = any("queue.ps1" in j["cmd"] for j in jobs)
    log = read_log(data / "queue.log", 4000)
    name, st = steps(data, root, alive, log)
    paths = sorted(data.glob("p2_v*.sqlite"))
    dbs = [db_stats(p) for p in paths]
    acts = [a for a in (activity(p) for p in paths) if a and a["recent"]]
    act = max(acts, key=lambda a: -a["recent"][0]["age_s"]) if acts else None
    return {"time": time.strftime("%H:%M:%S"), "name": name, "queue_alive": alive, "jobs": jobs, "steps": st,
            "gpu": gpu(), "gpu_history": gpu_history(), "services": services(), "dbs": [d for d in dbs if d],
            "scores": scores(root / "analysis"), "log": log[-25:],
            "live": live.live_jobs(db_path), "activity": act, "config": live.load_config(db_path),
            "installed": live.installed(), "pulls": live.pulls(), "benches": live.benches(db_path)}


def busy() -> bool:
    """A GPU job is running: the queue, a labeller, a scorer. Benches wait for this to clear."""
    return bool(processes())
