"""Page-level BM25 baseline over the pilot books (the floor the pipeline must beat).

Usage: python eval/baseline_bm25.py <text_dir>   (needs: pip install rank_bm25)
2026-11-01 result: right page in top 10 for 64/119 answerable questions, first for 23/119.
"""
import re, sys
from collections import defaultdict
from pathlib import Path
from rank_bm25 import BM25Okapi

sys.path.insert(0, str(Path(__file__).parent))
from gold_v0 import ITEMS
from verify_gold import norm

STOP = set("the a an of to and is in what does do how why i my for be are on with it that this by as at or not should someone about say says".split())

def tok(s):
    return [w for w in re.findall(r"[a-z]+", s.lower()) if w not in STOP]

def main():
    text_dir = Path(sys.argv[1])
    slugs = sorted({g["book"] for _, _, gold, _ in ITEMS for g in gold})
    docs, ids = [], []
    for s in slugs:
        for i, p in enumerate((text_dir / f"{s}.txt").read_text().split("\n\f")):
            docs.append(tok(norm(p))); ids.append((s, i + 1))
    bm = BM25Okapi(docs)
    per = defaultdict(lambda: [0, 0]); at1 = decoy_first = n = 0
    for q, kind, gold, decoys in ITEMS:
        if not gold:
            continue
        n += 1
        scores = bm.get_scores(tok(q))
        top = sorted(range(len(scores)), key=lambda i: -scores[i])[:10]
        want = {(g["book"], g["page"]) for g in gold}
        key = "cross-book" if kind == "comparative" else gold[0]["book"]
        per[key][0] += any(ids[i] in want for i in top); per[key][1] += 1
        at1 += ids[top[0]] in want
        decoy_first += bool(decoys) and ids[top[0]] == (gold[0]["book"], ids[top[0]][1]) and ids[top[0]][1] in decoys
    for k, (h, t) in sorted(per.items()):
        print(f"{k[:40]:40} recall@10 {h}/{t}")
    print(f"ALL recall@10 {sum(h for h, _ in per.values())}/{n}  recall@1 {at1}/{n}  decoy-first {decoy_first}")

if __name__ == "__main__":
    main()
