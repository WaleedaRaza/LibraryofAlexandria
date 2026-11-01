"""Retrieval ablation over the pilot gold set: which component buys what, per book and per question type.

Standalone on purpose (stdlib + numpy; talks to Ollama and the /rerank server over HTTP), so it runs against
any pipeline2 database without depending on the local models.py/s9_route.py version.

    python eval/ablate.py --db taxonomy-pipeline/data/p2.sqlite --out eval/results/ablation_v0.json
    python eval/ablate.py ... --no-models        # lexical configs only

Configs (every final list is zone-weighted the way S9 does it):
  lex_body        BM25 over unit text (+ spelling-normalised copy)
  lex_q           BM25 also over the generated questions (S9's lexical list)
  dense_u:<m>     cosine to unit vectors
  dense_q:<m>     cosine to generated-question vectors (max per unit)
  dense_uq:<m>    both, max per unit (S9's dense list)
  rrf_noq         RRF(lex_body, dense_u:qwen)      -- no generated questions anywhere
  rrf             RRF(lex_q, dense_uq:qwen)        -- S9 without rerank
  rrf+rr30        cross-encoder over rrf's top 30  -- S9 as configured
  rrf+rr50        cross-encoder over rrf's top 50
  rrf_noq+rr30    cross-encoder over rrf_noq's top 30
Output: per question, the top-50 unit ids per config and the rank of the first unit containing a gold anchor.
"""
from __future__ import annotations
import argparse
import array
import json
import math
import os
import re
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(os.environ.get("LIBXNDR_REPO") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT / "taxonomy-pipeline"))
from src.pipeline2.textnorm import match, search_copy  # noqa: E402

ZW = {"primary": 1.0, "apparatus": 0.35, "front": 0.25, "back": 0.25, "contents": 0.05}
STOP = set("""a an the of to and or is are was were be been in on at for with by as it its this that these those
what which who whom whose how why when where do does did i me my we our you your he she they them his her their
should would could can may might must about say says said tell according there here than then so not no""".split())
QWEN_PREFIX = "Instruct: Given a question, retrieve passages from books that answer it\nQuery: "
MODELS = {"qwen3-embedding:4b": QWEN_PREFIX, "bge-m3": "", "nomic-embed-text": "search_query: "}
K = 50


def post(url, body, timeout=300):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def terms(q):
    return [w for w in re.findall(r"[a-z]+", search_copy(q).lower()) if w not in STOP and len(w) > 1]


def bm25(con, q, with_q):
    t = terms(q)
    if not t:
        return []
    cols = "{body search questions}" if with_q else "{body search}"
    w = "0.0, 1.0, 1.0, 0.6" if with_q else "0.0, 1.0, 1.0, 0.0"
    rows = con.execute(f"SELECT unit_id, bm25(unit_fts, {w}) s FROM unit_fts WHERE unit_fts MATCH ? ORDER BY s LIMIT 200",
                       (f"{cols} : ({' OR '.join(chr(34) + x + chr(34) for x in t)})",)).fetchall()
    return [u for u, _ in rows]


class Dense:
    def __init__(self, con, model):
        rows = con.execute("SELECT v.unit_id, v.kind, v.vec, q.unit_id FROM unit_vec v LEFT JOIN unit_question q "
                           "ON v.kind='q' AND q.rowid = CAST(substr(v.unit_id, 3) AS INT) WHERE v.model=?", (model,)).fetchall()
        self.kind = np.array([k for _, k, _, _ in rows])
        self.ids = [(qu if k == "q" else u) for u, k, _, qu in rows]
        m = np.array([array.array("f", b) for _, _, b, _ in rows], dtype="float32")
        self.mat = m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-9)

    def search(self, qv, kinds):
        sims = self.mat @ qv
        mask = np.isin(self.kind, kinds)
        best = {}
        for i in np.argsort(-np.where(mask, sims, -9)):
            if not mask[i]:
                break
            u = self.ids[i]
            if u and u not in best:
                best[u] = float(sims[i])
            if len(best) >= 200:
                break
        return list(best)


def rrf(lists, zone):
    s = {}
    for lst in lists:
        for r, u in enumerate(lst):
            s[u] = s.get(u, 0.0) + 1.0 / (61 + r)
    return [u for u, _ in sorted(((u, v * ZW.get(zone[u], 0.5)) for u, v in s.items()), key=lambda x: -x[1])]


def rerank(url, q, ids, text, ref, zone, top):
    head, tail = ids[:top], ids[top:]
    docs = [f"{ref[u]}\n{text[u]}"[:2000] for u in head]
    data = post(url, {"query": q, "documents": docs, "texts": docs})
    rows = data.get("results", data.get("data", [])) if isinstance(data, dict) else data
    sc = [0.0] * len(head)
    for r in rows:
        sc[int(r["index"])] = float(r.get("relevance_score", r.get("score")))
    if any(x < 0 or x > 1 for x in sc):
        sc = [1 / (1 + math.exp(-x)) for x in sc]
    order = sorted(range(len(head)), key=lambda i: -sc[i] * ZW.get(zone[head[i]], 0.5))
    return [head[i] for i in order] + tail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--gold", default=str(ROOT / "eval" / "gold_v0.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "eval" / "results" / "ablation_v0.json"))
    ap.add_argument("--ollama", default="http://localhost:11434")
    ap.add_argument("--rerank-url", default="http://127.0.0.1:8088/rerank")
    ap.add_argument("--no-models", action="store_true")
    a = ap.parse_args()

    con = sqlite3.connect(a.db)
    gold = [json.loads(l) for l in Path(a.gold).read_text(encoding="utf-8").splitlines() if l.strip()]
    units = con.execute("SELECT id, edition_id, zone, ref, text FROM unit").fetchall()
    text = {u: t for u, _, _, _, t in units}
    ref = {u: r for u, _, _, r, _ in units}
    zone = {u: z for u, _, z, _, _ in units}
    norm = {u: match(t) for u, _, _, _, t in units}
    ed = {u: e for u, e, _, _, _ in units}
    have_models = [m for m in MODELS if not a.no_models and
                   con.execute("SELECT 1 FROM unit_vec WHERE model=? LIMIT 1", (m,)).fetchone()]
    dense = {m: Dense(con, m) for m in have_models}
    rr_ok = False
    if not a.no_models:
        try:
            rerank(a.rerank_url, "test", list(text)[:2], text, ref, zone, 2)
            rr_ok = True
        except Exception as e:
            print(f"rerank unavailable: {e}")

    out = {"db": a.db, "date": time.strftime("%Y-%m-%d %H:%M"), "models": have_models, "rerank": rr_ok, "questions": []}
    for n, g in enumerate(gold, 1):
        q = g["question"]
        golds = [u for u in text for x in g["gold"] if ed[u] == x["book"] and x["anchor"] in norm[u]]
        lists = {"lex_body": bm25(con, q, False), "lex_q": bm25(con, q, True)}
        for m, d in dense.items():
            qv = np.array(post(f"{a.ollama}/api/embed", {"model": m, "input": [MODELS[m] + q]})["embeddings"][0], "float32")
            qv /= np.linalg.norm(qv) + 1e-9
            lists[f"dense_u:{m}"] = d.search(qv, ["unit"])
            lists[f"dense_q:{m}"] = d.search(qv, ["q"])
            lists[f"dense_uq:{m}"] = d.search(qv, ["unit", "q"])
        final = {k: rrf([v], zone) for k, v in lists.items()}
        qw = "qwen3-embedding:4b"
        if qw in dense:
            final["rrf_noq"] = rrf([lists["lex_body"], lists[f"dense_u:{qw}"]], zone)
            final["rrf"] = rrf([lists["lex_q"], lists[f"dense_uq:{qw}"]], zone)
            if rr_ok:
                final["rrf+rr30"] = rerank(a.rerank_url, q, final["rrf"], text, ref, zone, 30)
                final["rrf+rr50"] = rerank(a.rerank_url, q, final["rrf"], text, ref, zone, 50)
                final["rrf_noq+rr30"] = rerank(a.rerank_url, q, final["rrf_noq"], text, ref, zone, 30)
        res = {"id": g["id"], "type": g["type"], "question": q, "books": sorted({x["book"] for x in g["gold"]}),
               "gold_units": sorted(set(golds)), "configs": {}}
        for k, lst in final.items():
            top = lst[:K]
            rank = next((i + 1 for i, u in enumerate(top) if u in golds), None)
            res["configs"][k] = {"rank": rank, "top": top}
        out["questions"].append(res)
        if n % 10 == 0:
            print(f"  {n}/{len(gold)}")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
