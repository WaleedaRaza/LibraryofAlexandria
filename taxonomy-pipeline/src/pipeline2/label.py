"""Passage typing (build-order step 4): one type per unit from the same set as question needs, pinned to a span.

    python -m src.pipeline2.label --db data/p2_v1.sqlite [--model gemma4:12b] [--limit N]

Types: instruction, argument, consolation, definition, example, story (+ other for front matter, lists, notes).
Every label carries an evidence quote that must occur in the unit (after normalisation); its char offsets
are stored. A label whose quote does not anchor is retried once, then stored with start = end = -1 (unpinned).
"""
from __future__ import annotations
import argparse
import json
import sqlite3
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import live
from .textnorm import match

TYPES = ["instruction", "argument", "consolation", "definition", "example", "story", "other"]
SCHEMA_SQL = """CREATE TABLE IF NOT EXISTS unit_label(unit_id TEXT PRIMARY KEY, type TEXT, type2 TEXT, confidence REAL,
    quote TEXT, start INT, end INT, model TEXT, created REAL);"""
SCHEMA = {"type": "object", "properties": {
    "type": {"type": "string", "enum": TYPES},
    "secondary": {"type": "string", "enum": TYPES + ["none"]},
    "confidence": {"type": "number"},
    "evidence": {"type": "string"}},
    "required": ["type", "secondary", "confidence", "evidence"]}
SYSTEM = (
    "You label passages of classic books by what the passage does for a reader. Reply with JSON only.\n"
    "type: instruction = tells the reader what to do or how to act; argument = gives reasons for a thesis, refutes, "
    "proves, or explains why; consolation = helps bear loss, death, illness or misfortune; definition = says what a term "
    "or thing is, lists its kinds or parts; example = an analogy, image, allegory or illustrative case serving a point; "
    "story = narrates events or scenes, what characters do or say; other = contents, notes, front matter, lists of "
    "references. Dialogue that reasons is argument; a myth or allegory told at length is story; a commentator explaining a "
    "line is the type of what he does.\n"
    "secondary: a second type if the passage clearly does two things, else none.\n"
    "confidence: 0 to 1.\n"
    "evidence: copy 5 to 25 consecutive words exactly from the passage that show the type. Copy, do not paraphrase.")


def _post(url, body, timeout=600):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _anchor(text: str, quote: str) -> tuple[int, int]:
    """Offsets of quote in text, compared in the normalised form; maps back by scanning (units are short)."""
    q = match(quote)
    if len(q) < 12:
        return -1, -1
    i = text.find(quote)
    if i >= 0:
        return i, i + len(quote)
    norm = match(text)
    j = norm.find(q)
    if j < 0:
        return -1, -1
    # map normalised offset back: walk prefixes (units are a few thousand chars at most)
    lo = 0
    for k in range(len(text)):
        if len(match(text[:k])) >= j:
            lo = k
            break
    for k in range(lo, len(text) + 1):
        if len(match(text[lo:k])) >= len(q):
            return lo, k
    return lo, len(text)


def _label_one(url, model, row):
    """One Ollama call (two tries when the quote does not anchor). Returns the unit_label row or None."""
    uid, text, ref, voice, vname, zone, title = row
    who = f" (speaker: commentator {vname})" if voice == "commentary" else ""
    user = f"Book: {title}\nLocation: {ref}{who}\n\nPassage:\n{text[:3500]}"
    out, s, e, err = None, -1, -1, None
    for _ in range(2):
        try:
            body = {"model": model, "stream": False, "think": False, "format": SCHEMA, "options": {"temperature": 0},
                    "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]}
            out = json.loads(_post(f"{url}/api/chat", body)["message"]["content"])
        except Exception as ex:
            err = ex
            continue
        s, e = _anchor(text, out.get("evidence", ""))
        if s >= 0:
            break
    if out is None:
        return None, err
    t2 = out.get("secondary")
    return (uid, out.get("type"), None if t2 in (None, "none", out.get("type")) else t2,
            float(out.get("confidence", 0) or 0), out.get("evidence", ""), s, e, model, time.time()), None


def run(con, url="http://localhost:11434", model="gemma4:12b", limit=None, log=print, workers=1, db=None) -> int:
    con.executescript(SCHEMA_SQL)
    rows = con.execute("SELECT u.id, u.text, u.ref, u.voice, u.voice_name, u.zone, json_extract(e.data,'$.detected_title') "
                       "FROM unit u JOIN edition e ON e.id=u.edition_id WHERE u.id NOT IN (SELECT unit_id FROM unit_label) "
                       "ORDER BY u.id" + (f" LIMIT {int(limit)}" if limit else "")).fetchall()
    t0, pinned, n = time.time(), 0, 0
    todo = []
    for row in rows:
        if row[5] in ("contents", "front"):
            con.execute("INSERT OR REPLACE INTO unit_label VALUES(?,?,?,?,?,?,?,?,?)",
                        (row[0], "other", None, 1.0, "", -1, -1, "rule", time.time()))
        else:
            todo.append(row)
    con.commit()

    def work(row):
        if db:
            live.beat(db, "types", model=model, unit=row[0], book=row[6], ref=row[2], text=row[1][:240], n=n, total=len(todo), workers=workers)
        return row, _label_one(url, model, row)

    # workers > 1 only pays when Ollama runs with OLLAMA_NUM_PARALLEL > 1; otherwise requests just queue
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for row, (rec, err) in pool.map(work, todo):
            n += 1
            if rec is None:
                log(f"  {row[0]}: {err}")
                continue
            pinned += rec[5] >= 0
            con.execute("INSERT OR REPLACE INTO unit_label VALUES(?,?,?,?,?,?,?,?,?)", rec)
            if n % 50 == 0:
                con.commit()
                log(f"  labelled {n}/{len(todo)}  {(time.time() - t0) / n:.1f}s each  pinned {pinned}")
    con.commit()
    if db:
        live.beat(db, "types", model=model, n=n, total=len(todo), done=True)
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--ollama", default="http://localhost:11434")
    ap.add_argument("--model", default=None, help="default: data/pipeline_config.json 'types' (the dashboard form)")
    ap.add_argument("--workers", type=int, default=None, help="parallel requests; default from pipeline_config.json")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    con = sqlite3.connect(a.db)
    model, workers = live.model_for(a.db, "types", a.model), live.workers_for(a.db, "types", a.workers)
    print(f"typing with {model}, {workers} worker(s)")
    n = run(con, a.ollama, model, a.limit, workers=workers, db=a.db)
    dist = con.execute("SELECT type, count(*), sum(start>=0) FROM unit_label GROUP BY type ORDER BY 2 DESC").fetchall()
    print(f"labelled {n} units; type, count, pinned: {dist}")


if __name__ == "__main__":
    main()
