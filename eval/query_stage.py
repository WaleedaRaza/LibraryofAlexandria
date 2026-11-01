"""Build-order steps 2 and 3: classify each question's need, rewrite it into the books' vocabularies, re-rank.

    python eval/query_stage.py plan  --out analysis/query_plans_v1.json             # gemma4, one call per question
    python eval/query_stage.py need  --plans analysis/query_plans_v1.json           # step 2 check vs eval/need_labels_v0.json
    python eval/query_stage.py score --db data/p2_v1.sqlite --plans analysis/query_plans_v1.json --out analysis/rewrite_v1.json

Variants scored (all end with the cross-encoder over the fused top 30, as S9 does):
  base        RRF(bm25+questions, dense qwen) on the question alone            -- the 62/119 baseline
  rewrites    RRF over the question and every rewrite, each through both retrievers
  rewrites+bk the same, with units from books the question names kept and others' rerank scores halved
              (comparative questions and questions naming no book are left alone)
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ablate  # noqa: E402  (same folder: bm25, Dense, rrf, rerank, post, match)

NEEDS = ["instruction", "argument", "consolation", "definition", "example", "story"]
LIBRARY = [
    ("plato-the-republic-0820a029", "Plato, The Republic (Jowett translation, 1871)", ["plato", "socrates", "republic", "thrasymachus", "glaucon", "cephalus"]),
    ("ethics-spinoza-v-2-8b9cd642", "Aristotle, Nicomachean Ethics (W. D. Ross translation)", ["aristotle", "nicomachean"]),
    ("benedict-spinoza-ethics-6a160dca", "Spinoza, Ethics (R. H. M. Elwes translation, 1883)", ["spinoza"]),
    ("leviathan-thomas-hobbes-dup-2-b557507d", "Hobbes, Leviathan (1651 English, original spelling)", ["hobbes", "leviathan"]),
    ("on-liberty-john-stuart-mill-c4c2ab9b", "John Stuart Mill, On Liberty (1859)", ["mill", "on liberty"]),
    ("enchiridion-epictetus-efc959a4", "Epictetus, Enchiridion (a modern English translation arranged by stages)", ["epictetus", "enchiridion"]),
    ("the-art-of-war-sun-tzu-48a70911", "Sun Tzu, The Art of War (Lionel Giles translation, 1910, with Chinese commentators)", ["sun tzu", "art of war", "chang yu", "tu mu", "ts'ao kung"]),
    ("crime-and-punishment-fyodor-dostoevsky-8f040fe5", "Dostoevsky, Crime and Punishment (Constance Garnett translation)", ["dostoevsky", "raskolnikov", "sonia", "svidrigailov", "marmeladov", "porfiry", "dounia", "razumihin", "pawnbroker"]),
]
SYSTEM = (
    "You help a reader find passages in a small library of classic books. Reply with JSON only.\n"
    "Library:\n" + "\n".join(f"- {t}" for _, t, _ in LIBRARY) + "\n\n"
    "For the reader's question:\n"
    "1. need: what kind of passage would satisfy them. instruction = practical advice on what to do; "
    "argument = reasons, a thesis and its support, why something is so; consolation = comfort or a way to bear "
    "a loss, death, illness or misfortune; definition = what a term or thing is, its kinds or parts; "
    "example = an analogy, image or illustrative case; story = events, scenes, what characters say or do, myths.\n"
    "2. rewrites: 3 to 5 search queries that say the same thing in the words these books actually use: their "
    "translators' diction, period spelling where relevant (Hobbes: 'warre', 'covenants', 'the condition of meer nature'), "
    "technical terms (Spinoza: 'conatus', 'affects', 'adequate ideas'; Epictetus: 'what is in our power', 'impressions'), "
    "character names in full (Raskolnikov's mother is Pulcheria Alexandrovna). At least one rewrite is a short declarative "
    "sentence the book itself might contain. Do not answer the question and do not invent quotations.\n"
    "3. books: which library books the question names or clearly points to, as numbers from the list starting at 1; "
    "empty if none or if it is about several books."
)
SCHEMA = {"type": "object", "properties": {
    "need": {"type": "string", "enum": NEEDS},
    "rewrites": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 5},
    "books": {"type": "array", "items": {"type": "integer"}}},
    "required": ["need", "rewrites", "books"]}


def chat(url, model, user):
    body = {"model": model, "stream": False, "think": False, "format": SCHEMA, "options": {"temperature": 0},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]}
    return json.loads(ablate.post(f"{url}/api/chat", body)["message"]["content"])


def cmd_plan(a):
    gold = [json.loads(l) for l in Path(a.gold).read_text(encoding="utf-8").splitlines() if l.strip()]
    out = json.loads(Path(a.out).read_text(encoding="utf-8")) if Path(a.out).exists() else {}
    t0 = time.time()
    for g in gold:
        if g["id"] in out:
            continue
        for attempt in range(3):
            try:
                p = chat(a.ollama, a.model, g["question"])
                break
            except Exception as e:
                p = {"error": str(e)}
        p["books"] = [LIBRARY[i - 1][0] for i in p.get("books", []) if isinstance(i, int) and 1 <= i <= len(LIBRARY)]
        out[g["id"]] = {"question": g["question"], **p}
        Path(a.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"planned {len(out)} questions in {time.time() - t0:.0f}s ({(time.time() - t0) / max(len(gold), 1):.1f}s each)")


def cmd_need(a):
    plans = json.loads(Path(a.plans).read_text(encoding="utf-8"))
    labels = json.loads(Path(a.labels).read_text(encoding="utf-8"))["labels"]
    agree, conf, rows = 0, Counter(), []
    for qid, lab in sorted(labels.items()):
        got = plans.get(qid, {}).get("need")
        ok = got in lab
        agree += ok
        conf[(lab[0], got if ok is False else lab[0])] += 1
        if not ok:
            rows.append(f"| {qid} | {plans[qid]['question']} | {'/'.join(lab)} | {got} |")
    print(f"need agreement: {agree}/{len(labels)} (check: >=100)\n")
    print("| hand label | " + " | ".join(NEEDS) + " |\n| --- |" + " --- |" * len(NEEDS))
    for h in NEEDS:
        print(f"| {h} | " + " | ".join(str(conf[(h, m)]) for m in NEEDS) + " |")
    print("\n| id | question | hand | gemma |\n| --- | --- | --- | --- |\n" + "\n".join(rows))


def cmd_score(a):
    import sqlite3
    con = sqlite3.connect(a.db)
    plans = json.loads(Path(a.plans).read_text(encoding="utf-8"))
    gold = [json.loads(l) for l in Path(a.gold).read_text(encoding="utf-8").splitlines() if l.strip()]
    units = con.execute("SELECT id, edition_id, zone, ref, text FROM unit").fetchall()
    text = {u: t for u, _, _, _, t in units}
    ref = {u: r for u, _, _, r, _ in units}
    zone = {u: z for u, _, z, _, _ in units}
    ed = {u: e for u, e, _, _, _ in units}
    norm = {u: ablate.match(t) for u, t in text.items()}
    qw = "qwen3-embedding:4b"
    dense = ablate.Dense(con, qw)

    def emb(s):
        v = np.array(ablate.post(f"{a.ollama}/api/embed", {"model": qw, "input": [ablate.QWEN_PREFIX + s]})["embeddings"][0], "float32")
        return v / (np.linalg.norm(v) + 1e-9)

    def lists_for(s):
        return [ablate.bm25(con, s, True), dense.search(emb(s), ["unit", "q"])]

    def rr_scores(q, ids):
        head = ids[:30]
        docs = [f"{ref[u]}\n{text[u]}"[:2000] for u in head]
        data = ablate.post(a.rerank_url, {"query": q, "documents": docs, "texts": docs})
        rows = data.get("results", data.get("data", [])) if isinstance(data, dict) else data
        sc = [0.0] * len(head)
        for r in rows:
            sc[int(r["index"])] = float(r.get("relevance_score", r.get("score")))
        if any(x < 0 or x > 1 for x in sc):
            sc = [1 / (1 + np.exp(-x)) for x in sc]
        return {u: s * ablate.ZW.get(zone[u], 0.5) for u, s in zip(head, sc)}

    def order(scores, ids):
        head = sorted(scores, key=lambda u: -scores[u])
        return head + [u for u in ids if u not in scores]

    res, t0 = [], time.time()
    for g in gold:
        if not g["gold"]:
            continue
        p = plans[g["id"]]
        golds = {u for u in text for x in g["gold"] if ed[u] == x["book"] and x["anchor"] in norm[u]}
        base_lists = lists_for(g["question"])
        rw_lists = base_lists + [l for s in p.get("rewrites", [])[:5] for l in lists_for(s)]
        v = {}
        fb = ablate.rrf(base_lists, zone)
        v["base"] = order(rr_scores(g["question"], fb), fb)
        fr = ablate.rrf(rw_lists, zone)
        sr = rr_scores(g["question"], fr)
        v["rewrites"] = order(sr, fr)
        named = set(p.get("books", []))
        if named and g["type"] != "comparative":
            v["rewrites+bk"] = order({u: s * (1.0 if ed[u] in named else 0.5) for u, s in sr.items()}, fr)
        else:
            v["rewrites+bk"] = v["rewrites"]
        v["rewrites_norr"] = fr
        row = {"id": g["id"], "type": g["type"], "need": p.get("need"), "book": g["gold"][0]["book"], "ranks": {}}
        for k, lst in v.items():
            row["ranks"][k] = next((i + 1 for i, u in enumerate(lst[:50]) if u in golds), None)
        res.append(row)
    secs = (time.time() - t0) / max(len(res), 1)
    Path(a.out).write_text(json.dumps(res, indent=1), encoding="utf-8")
    ks = list(res[0]["ranks"])
    print(f"{len(res)} scored questions, {secs:.1f}s per question\n\n| variant | ranked first | top 10 |\n| --- | --- | --- |")
    for k in ks:
        r = [x["ranks"][k] for x in res]
        print(f"| {k} | {sum(1 for y in r if y == 1)} | {sum(1 for y in r if y and y <= 10)} |")
    by = defaultdict(list)
    for x in res:
        by[x["type"]].append(x)
    print("\n| question type | n | " + " | ".join(f"{k} #1" for k in ks) + " |\n| --- | --- |" + " --- |" * len(ks))
    for t, xs in sorted(by.items()):
        print(f"| {t} | {len(xs)} | " + " | ".join(str(sum(1 for x in xs if x['ranks'][k] == 1)) for k in ks) + " |")


def main():
    root = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "need", "score"):
        s = sub.add_parser(name)
        s.add_argument("--gold", default=str(root / "gold_v0.jsonl"))
        s.add_argument("--ollama", default="http://localhost:11434")
        s.add_argument("--model", default="gemma4:12b")
        s.add_argument("--rerank-url", default="http://127.0.0.1:8088/rerank")
        s.add_argument("--labels", default=str(root / "need_labels_v0.json"))
        s.add_argument("--plans", default="analysis/query_plans_v1.json")
        s.add_argument("--out", default="analysis/query_plans_v1.json" if name == "plan" else "analysis/rewrite_v1.json")
        s.add_argument("--db", default=None)
    a = ap.parse_args()
    {"plan": cmd_plan, "need": cmd_need, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    main()
