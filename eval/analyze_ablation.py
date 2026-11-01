"""Tables and an automatic failure tagging for eval/ablate.py output.

    python eval/analyze_ablation.py --db taxonomy-pipeline/data/p2.sqlite --abl eval/results/ablation_v0.json \
        --md eval/results/ablation_v0.md

Scored items: questions with a gold passage (unanswerable ones are reported separately).
Failure tags for a miss (gold not in the top 10), first matching tag wins:
  parsing      the gold unit carries a parse defect that changes its score: a non-primary zone
               (down-weighted) or a division label repeated across parts (Spinoza's "Preface")
  granularity  a unit next to a gold unit is in the top 10 (the answer sits across a unit boundary)
  vocabulary   under a third of the question's content words (stemmed) occur in any gold unit
  decoy        the top hit is on a page the gold set marks as a decoy
  wrong-book   no top-10 unit comes from a gold book
  ranking      everything else: right book in the top 10, the passage outranked
"""
from __future__ import annotations
import argparse
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

STOP = set("""a an the of to and or is are was were be been in on at for with by as it its this that these those
what which who whom whose how why when where do does did i me my we our you your he she they them his her their
should would could can may might must about say says said tell according there here than then so not no one
""".split())


def stem(w: str) -> str:
    for suf in ("ings", "ing", "edly", "ed", "ies", "es", "s", "ly"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


def words(s: str) -> set[str]:
    return {stem(w) for w in re.findall(r"[a-z]+", s.lower()) if w not in STOP and len(w) > 2}


def metrics(ranks):
    n = len(ranks)
    r1 = sum(1 for r in ranks if r == 1)
    r10 = sum(1 for r in ranks if r and r <= 10)
    r50 = sum(1 for r in ranks if r)
    mrr = sum(1 / r for r in ranks if r and r <= 10) / max(n, 1)
    return n, r1, r10, r50, mrr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--abl", required=True)
    ap.add_argument("--md", default=None)
    ap.add_argument("--tag-config", default=None, help="config whose misses get tagged (default: best r@10)")
    a = ap.parse_args()
    con = sqlite3.connect(a.db)
    abl = json.loads(Path(a.abl).read_text(encoding="utf-8"))
    gold_items = {json.loads(l)["id"]: json.loads(l) for l in
                  (Path(a.abl).parents[2] / "eval" / "gold_v0.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()} \
        if (Path(a.abl).parents[2] / "eval" / "gold_v0.jsonl").exists() else {}
    U = {r[0]: r for r in con.execute(
        "SELECT u.id, u.edition_id, u.zone, u.text, u.page_start, u.page_end, u.start, d.label FROM unit u "
        "JOIN division d ON d.edition_id=u.edition_id AND d.id=u.division_id")}
    order = defaultdict(list)
    for uid, e, *_rest in sorted(U.values(), key=lambda r: (r[1], r[6])):
        order[e].append(uid)
    pos = {u: (e, i) for e, lst in order.items() for i, u in enumerate(lst)}
    rep_labels = {(e, l) for e, l, c in con.execute(
        "SELECT edition_id, label, count(*) FROM division WHERE zone='primary' GROUP BY 1,2") if c > 1}

    scored = [q for q in abl["questions"] if q["books"]]
    configs = list(scored[0]["configs"]) if scored else []
    lines = [f"# Retrieval ablation, gold_v0 ({len(scored)} scored questions)", "",
             f"Run {abl['date']}; models: {', '.join(abl['models']) or 'none'}; rerank: {abl['rerank']}.", "",
             "## Overall", "", "| config | top-1 | top-10 | top-50 | MRR@10 |", "| --- | --- | --- | --- | --- |"]
    best, best_r10 = None, -1
    for c in configs:
        n, r1, r10, r50, mrr = metrics([q["configs"][c]["rank"] for q in scored])
        lines.append(f"| {c} | {r1} | {r10} | {r50} | {mrr:.3f} |")
        if r10 > best_r10 or (r10 == best_r10 and best and r1 > metrics([q['configs'][best]['rank'] for q in scored])[1]):
            best, best_r10 = c, r10
    union = sum(1 for q in scored if any(q["configs"][c]["rank"] for c in configs))
    union10 = sum(1 for q in scored if any((q["configs"][c]["rank"] or 99) <= 10 for c in configs))
    lines += ["", f"Oracle over all configs: {union10}/{len(scored)} have the gold unit in some config's top 10, "
                  f"{union}/{len(scored)} in some top 50.", ""]

    for title, key in (("By question type (top-10)", lambda q: q["type"]),
                       ("By book (top-10; comparative questions count once, under cross-book)",
                        lambda q: "cross-book" if q["type"] == "comparative" else q["books"][0])):
        groups = defaultdict(list)
        for q in scored:
            groups[key(q)].append(q)
        lines += [f"## {title}", "", "| group | n | " + " | ".join(configs) + " |",
                  "| --- | --- | " + " | ".join("---" for _ in configs) + " |"]
        for g in sorted(groups):
            qs = groups[g]
            cells = [f"{metrics([q['configs'][c]['rank'] for q in qs])[2]}" for c in configs]
            lines.append(f"| {g[:40]} | {len(qs)} | " + " | ".join(cells) + " |")
        lines.append("")

    tag_cfg = a.tag_config or best
    tags, rows = Counter(), []
    for q in scored:
        r = q["configs"][tag_cfg]["rank"]
        if r and r <= 10:
            continue
        top = q["configs"][tag_cfg]["top"][:10]
        golds = q["gold_units"]
        gi = gold_items.get(q["id"], {})
        decoys = set(gi.get("decoy_pages", []))
        qw = words(q["question"])
        cover = max((len(qw & words(U[g][3])) / max(len(qw), 1) for g in golds), default=0)
        adj = {order[pos[g][0]][j] for g in golds for j in (pos[g][1] - 1, pos[g][1] + 1)
               if 0 <= j < len(order[pos[g][0]])}
        # running-header residue is present in most Republic units but adds only 'http www idph net' tokens,
        # so it is not counted as a cause; a wrong zone or a wrong division label changes scores directly
        defect = [g for g in golds if U[g][2] != "primary" or (U[g][1], U[g][7]) in rep_labels]
        if defect:
            t = "parsing"
        elif adj & set(top):
            t = "granularity"
        elif cover < 1 / 3:
            t = "vocabulary"
        elif top and decoys and any(U[top[0]][4] <= d <= U[top[0]][5] for d in decoys) and U[top[0]][1] in q["books"]:
            t = "decoy"
        elif not any(U[u][1] in q["books"] for u in top):
            t = "wrong-book"
        else:
            t = "ranking"
        tags[t] += 1
        rows.append((q["id"], q["type"], t, r, f"{cover:.2f}", q["question"],
                     f"{U[top[0]][1][:18]} p{U[top[0]][4]}" if top else "-"))
    lines += [f"## Misses in {tag_cfg} (gold not in top 10): {sum(tags.values())}", "",
              "| tag | count |", "| --- | --- |"] + [f"| {t} | {c} |" for t, c in tags.most_common()] + [
              "", "| id | type | tag | rank | word cover | question | top hit |", "| --- | --- | --- | --- | --- | --- | --- |"]
    lines += [f"| {i} | {ty} | {t} | {r or '>50'} | {c} | {qq} | {th} |" for i, ty, t, r, c, qq, th in rows]
    md = "\n".join(lines) + "\n"
    if a.md:
        Path(a.md).write_text(md, encoding="utf-8")
    print(md)


if __name__ == "__main__":
    main()
