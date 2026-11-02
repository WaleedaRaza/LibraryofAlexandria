"""Fine-tune the cross-encoder reranker in-domain on generated questions (build-order step 6b).

    python eval/finetune_reranker.py --db data/p2_v1.sqlite --out models/bge-reranker-libxndr-v1 [--neg 3 --epochs 1]

Why: the listwise LLM judge (gemma4:12b over the top ten) ranked worse than bge-reranker-v2-m3 (53 vs 60 first of 119).
Gold is in the top three for 83/119, so the fight is over near-ties, and the reranker is the component that decides them.
S7 left 10,211 generated questions for the pilot, each tied to the passage it was written from: that is an in-domain
training set the base reranker never saw (classic prose, archaic vocabulary, editor's apparatus as distractors).

Training pairs: (generated question, its passage) = positive; hard negatives = BM25 neighbours of the question over
passage text only (not the generated-question column, which would leak the query), two from the same book (other divisions) and one
from another, formatted exactly as the serving reranker sees documents (ref + newline + text, cut at 2000 chars).
Gold questions are never used for training; they stay the test set (eval/query_stage.py score).

Output: a model directory the reranker server can load in place of BAAI/bge-reranker-v2-m3, plus a held-out
pairwise accuracy (positive scores above each hard negative) before and after, so the run reports a number.
GPU: ~570M parameters, fp16, batch 8 at 512 tokens fits a 16 GB card; ~25 min per epoch on 40k pairs. Run it alone.
"""
from __future__ import annotations
import argparse
import json
import random
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ablate  # noqa: E402

DOC_CUT = 2000


def doc(ref: str, text: str) -> str:
    return f"{ref}\n{text}"[:DOC_CUT]


def build_pairs(con, neg_per=3, limit=0, seed=7):
    rnd = random.Random(seed)
    units = {u: (e, r, t, d) for u, e, r, t, d in con.execute("SELECT id, edition_id, ref, text, division_id FROM unit WHERE zone='primary'")}
    rows = con.execute("SELECT q.unit_id, q.question FROM unit_question q JOIN unit u ON u.id=q.unit_id WHERE u.zone='primary'").fetchall()
    rnd.shuffle(rows)
    if limit:
        rows = rows[:limit]
    pairs, skipped = [], 0
    for i, (uid, q) in enumerate(rows):
        e, r, t, d = units[uid]
        cands = [c for c in ablate.bm25(con, q, with_q=False) if c != uid and c in units]
        # same book but another division: lexically close, yet unlikely to answer the same question (a neighbour in the
        # same chapter often does, and would be a false negative)
        same = [c for c in cands if units[c][0] == e and units[c][3] != d][:2]
        other = [c for c in cands if units[c][0] != e][:1]
        negs = (same + other)[:neg_per]
        if len(negs) < 2:
            skipped += 1
            continue
        pairs.append({"q": q, "pos": doc(r, t), "negs": [doc(units[c][1], units[c][2]) for c in negs], "unit": uid})
        if (i + 1) % 1000 == 0:
            print(f"  pairs {i + 1}/{len(rows)}", flush=True)
    print(f"{len(pairs)} questions with hard negatives ({skipped} skipped for lack of BM25 neighbours)")
    return pairs


def pairwise_acc(model, held, batch=32) -> float:
    """Share of (positive, negative) pairs where the positive scores higher."""
    qs, ds, idx = [], [], []
    for k, p in enumerate(held):
        for d in [p["pos"]] + p["negs"]:
            qs.append(p["q"]); ds.append(d); idx.append(k)
    scores = model.predict(list(zip(qs, ds)), batch_size=batch, show_progress_bar=False)
    by = {}
    for k, s in zip(idx, scores):
        by.setdefault(k, []).append(float(s))
    wins = total = 0
    for k, sc in by.items():
        for n in sc[1:]:
            total += 1
            wins += sc[0] > n
    return wins / max(total, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--base", default="BAAI/bge-reranker-v2-m3")
    ap.add_argument("--neg", type=int, default=3)
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--max-len", type=int, default=512)
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--limit", type=int, default=0, help="questions to use (0 = all)")
    ap.add_argument("--holdout", type=float, default=0.05)
    ap.add_argument("--pairs-only", action="store_true", help="build and save pairs, do not train")
    a = ap.parse_args()

    con = sqlite3.connect(a.db)
    t0 = time.time()
    pairs = build_pairs(con, a.neg, a.limit)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "pairs.jsonl").write_text("\n".join(json.dumps(p, ensure_ascii=False) for p in pairs), encoding="utf-8")
    print(f"pairs built in {time.time() - t0:.0f}s -> {out / 'pairs.jsonl'}")
    if a.pairs_only:
        return

    from sentence_transformers import CrossEncoder, InputExample
    from torch.utils.data import DataLoader

    n_hold = max(50, int(len(pairs) * a.holdout))
    held, train = pairs[:n_hold], pairs[n_hold:]
    model = CrossEncoder(a.base, num_labels=1, max_length=a.max_len)
    before = pairwise_acc(model, held)
    print(f"held-out pairwise accuracy before: {before:.3f} ({n_hold} questions)", flush=True)

    examples = []
    for p in train:
        examples.append(InputExample(texts=[p["q"], p["pos"]], label=1.0))
        for d in p["negs"]:
            examples.append(InputExample(texts=[p["q"], d], label=0.0))
    random.Random(7).shuffle(examples)
    loader = DataLoader(examples, shuffle=True, batch_size=a.batch)
    print(f"training on {len(examples)} pairs, {a.epochs} epoch(s), batch {a.batch}", flush=True)
    model.fit(train_dataloader=loader, epochs=a.epochs, warmup_steps=int(0.1 * len(loader)),
              optimizer_params={"lr": a.lr}, use_amp=True, show_progress_bar=True)
    model.save(str(out))
    after = pairwise_acc(model, held)
    print(f"held-out pairwise accuracy after: {after:.3f} (before {before:.3f})")
    (out / "report.json").write_text(json.dumps({"base": a.base, "questions": len(pairs), "train_pairs": len(examples),
                                                 "holdout": n_hold, "acc_before": before, "acc_after": after,
                                                 "epochs": a.epochs, "secs": round(time.time() - t0)}, indent=1))
    print(f"saved {out}; point the reranker server at it and rerun: python eval/query_stage.py score --out analysis/rerank_ft_v1.json")


if __name__ == "__main__":
    main()
