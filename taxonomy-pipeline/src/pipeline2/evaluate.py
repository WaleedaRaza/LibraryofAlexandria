"""Score routing against eval/gold_v0.py (unit level).

hit@k: some top-k unit contains a gold anchor (after `textnorm.match`).
decoy-first: the top unit sits on a decoy page and contains no gold anchor.
coverage: every anchor must lie inside exactly one unit (tests S3 + S6).
"""
from __future__ import annotations
import importlib.util
from collections import defaultdict
from pathlib import Path

from .s9_route import route
from .textnorm import match


def load_gold(path: str | Path):
    spec = importlib.util.spec_from_file_location("gold", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.ITEMS


def run(con, gold_path, k: int = 10, emb=None, verbose: bool = False, log=print, rerank=None) -> dict:
    items = load_gold(gold_path)
    units = con.execute("SELECT id, edition_id, page_start, page_end, text FROM unit").fetchall()
    norm = {u[0]: match(u[4]) for u in units}
    meta = {u[0]: u for u in units}
    have = {r[0] for r in con.execute("SELECT id FROM edition")}

    # coverage
    missing = []
    for q, kind, gold, _ in items:
        for g in gold:
            if g["book"] in have and not any(g["anchor"] in norm[u[0]] for u in units if u[1] == g["book"]):
                missing.append((g["book"], g["page"], g["anchor"][:50]))

    per = defaultdict(lambda: [0, 0])
    at1 = n = decoy_first = abstain_ok = 0
    rr = 0.0
    misses = []
    for q, kind, gold, decoys in items:
        if not gold:
            hits = route(con, q, k=k, emb=emb, rerank=rerank)
            abstain_ok += not hits      # BM25 alone will rarely abstain; scored once a threshold exists
            continue
        if not any(g["book"] in have for g in gold):
            continue
        n += 1
        hits = route(con, q, k=k, emb=emb, rerank=rerank)
        rank = next((i for i, h in enumerate(hits)
                     if any(g["book"] == h.edition_id and g["anchor"] in norm[h.unit_id] for g in gold)), None)
        key = "cross-book" if kind == "comparative" else gold[0]["book"]
        per[key][1] += 1
        if rank is not None:
            per[key][0] += 1
            rr += 1.0 / (rank + 1)
            at1 += rank == 0
        else:
            misses.append((q, [f"{h.edition_id[:14]} p{h.page_start} {h.zone}" for h in hits[:3]]))
        if decoys and hits:
            top = hits[0]
            if top.edition_id == gold[0]["book"] and rank != 0 and any(top.page_start <= d <= top.page_end for d in decoys):
                decoy_first += 1
    total = sum(h for h, _ in per.values())
    res = {"n": n, "recall@k": total, "recall@1": at1, "mrr": round(rr / max(n, 1), 3), "decoy_first": decoy_first,
           "anchors_not_in_units": missing, "per_book": {k_: tuple(v) for k_, v in sorted(per.items())}}
    if verbose:
        for m in misses:
            log(f"MISS {m}")
    return res
