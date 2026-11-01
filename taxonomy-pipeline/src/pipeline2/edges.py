"""Passage edges (build-order step 7): claims per passage, then typed cross-book edges between claims.

    python -m src.pipeline2.edges claims --db data/p2_v1.sqlite [--limit N]     # gemma: 1-3 claims per labelled passage
    python -m src.pipeline2.edges embed  --db ...                                 # qwen3 vectors for every claim
    python -m src.pipeline2.edges pair   --db ... [--k 4] [--min 0.6]             # cross-book candidate pairs by cosine
    python -m src.pipeline2.edges judge  --db ... [--limit N]                     # gemma: same_idea / argues_against / example_of / none
    python -m src.pipeline2.edges sample --db ... --n 200 --out analysis/edges_sample.md
    python -m src.pipeline2.edges stats  --db ...

Every claim is pinned to an evidence quote in its passage (start/end offsets, -1 if the quote did not anchor).
An edge is stored only when the judge names a relation other than none; "none" verdicts are kept in claim_pair so a
rerun does not re-judge them. example_of is directed: src exemplifies dst.
"""
from __future__ import annotations
import argparse
import array
import json
import random
import sqlite3
import time
import urllib.request

import numpy as np

from .label import _anchor, _post

CLAIM_TYPES = ("argument", "instruction", "definition", "consolation", "example")   # story passages carry no claims
RELS = ["same_idea", "argues_against", "src_exemplifies_dst", "dst_exemplifies_src", "none"]
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS unit_claim(id INTEGER PRIMARY KEY, unit_id TEXT, claim TEXT, quote TEXT, start INT, end INT,
    model TEXT, created REAL);
CREATE INDEX IF NOT EXISTS unit_claim_unit ON unit_claim(unit_id);
CREATE TABLE IF NOT EXISTS claim_done(unit_id TEXT PRIMARY KEY, n INT);
CREATE TABLE IF NOT EXISTS claim_vec(claim_id INTEGER PRIMARY KEY, model TEXT, vec BLOB);
CREATE TABLE IF NOT EXISTS claim_pair(src INTEGER, dst INTEGER, cos REAL, rel TEXT, reason TEXT, confidence REAL,
    model TEXT, created REAL, PRIMARY KEY(src, dst));
"""
CLAIM_SCHEMA = {"type": "object", "properties": {"claims": {"type": "array", "maxItems": 3, "items": {
    "type": "object", "properties": {"claim": {"type": "string"}, "evidence": {"type": "string"}},
    "required": ["claim", "evidence"]}}}, "required": ["claims"]}
CLAIM_SYSTEM = (
    "Extract the claims a passage of a classic book makes. Reply with JSON only.\n"
    "A claim is one plain declarative sentence in modern English, at most 25 words, stating what the author asserts, "
    "advises or defines, with the subject named (not 'he' or 'it'). Give 1 to 3 claims, the most central first. "
    "Do not summarise the narrative, do not add your own view, do not merge two claims into one.\n"
    "evidence: copy 5 to 25 consecutive words exactly from the passage that carry the claim. Copy, do not paraphrase.\n"
    "If the passage makes no claim (a list, a heading, pure narration), return an empty list.")
JUDGE_SCHEMA = {"type": "object", "properties": {
    "relation": {"type": "string", "enum": RELS}, "confidence": {"type": "number"}, "reason": {"type": "string"}},
    "required": ["relation", "confidence", "reason"]}
JUDGE_SYSTEM = (
    "Two passages from different classic books are given, each with a claim drawn from it. Decide how claim A (from "
    "passage A) relates to claim B (from passage B). Reply with JSON only.\n"
    "same_idea: both assert substantially the same thing, allowing for different vocabulary and framing.\n"
    "argues_against: one denies, refutes or recommends the opposite of what the other asserts, on the same question.\n"
    "src_exemplifies_dst: A is a concrete case, image or story that illustrates the general point B makes.\n"
    "dst_exemplifies_src: B is a concrete case, image or story that illustrates the general point A makes.\n"
    "none: they share words or a topic but neither agree, oppose nor illustrate each other, or one is too vague to tell.\n"
    "Be strict: shared topic is not same_idea; a different emphasis is not argues_against. Most pairs are none.\n"
    "reason: at most 20 words, naming what the two passages actually say.")


def _embed(url, model, texts):
    out = _post(f"{url}/api/embed", {"model": model, "input": texts})["embeddings"]
    m = np.array(out, dtype="float32")
    m /= np.linalg.norm(m, axis=1, keepdims=True) + 1e-9
    return m


def cmd_claims(con, a, log=print):
    rows = con.execute(
        "SELECT u.id, u.text, u.ref, u.voice, u.voice_name, json_extract(e.data,'$.detected_title'), l.type FROM unit u "
        "JOIN unit_label l ON l.unit_id=u.id JOIN edition e ON e.id=u.edition_id "
        "WHERE u.zone='primary' AND l.type IN (%s) AND u.id NOT IN (SELECT unit_id FROM claim_done) ORDER BY u.id"
        % ",".join("?" * len(CLAIM_TYPES)) + (f" LIMIT {int(a.limit)}" if a.limit else ""), CLAIM_TYPES).fetchall()
    t0, made, pinned = time.time(), 0, 0
    for n, (uid, text, ref, voice, vname, title, typ) in enumerate(rows, 1):
        who = f" (speaker: commentator {vname})" if voice == "commentary" else ""
        user = f"Book: {title}\nLocation: {ref}{who}\nPassage type: {typ}\n\nPassage:\n{text[:3500]}"
        body = {"model": a.model, "stream": False, "think": False, "format": CLAIM_SCHEMA, "options": {"temperature": 0},
                "messages": [{"role": "system", "content": CLAIM_SYSTEM}, {"role": "user", "content": user}]}
        try:
            out = json.loads(_post(f"{a.ollama}/api/chat", body)["message"]["content"])
        except Exception as ex:
            log(f"  {uid}: {ex}")
            continue
        k = 0
        for c in out.get("claims", [])[:3]:
            claim, quote = (c.get("claim") or "").strip(), c.get("evidence") or ""
            if len(claim.split()) < 4:
                continue
            s, e = _anchor(text, quote)
            pinned += s >= 0
            con.execute("INSERT INTO unit_claim(unit_id, claim, quote, start, end, model, created) VALUES(?,?,?,?,?,?,?)",
                        (uid, claim, quote, s, e, a.model, time.time()))
            k += 1
        made += k
        con.execute("INSERT OR REPLACE INTO claim_done VALUES(?,?)", (uid, k))
        if n % 25 == 0:
            con.commit()
            log(f"  claims {n}/{len(rows)} units, {made} claims ({pinned} pinned), {(time.time() - t0) / n:.1f}s per unit")
    con.commit()
    log(f"claims: {len(rows)} units, {made} claims, {pinned} pinned, {time.time() - t0:.0f}s")


def cmd_embed(con, a, log=print):
    rows = con.execute("SELECT id, claim FROM unit_claim WHERE id NOT IN (SELECT claim_id FROM claim_vec) ORDER BY id").fetchall()
    for i in range(0, len(rows), 32):
        chunk = rows[i:i + 32]
        m = _embed(a.ollama, a.embed_model, [c for _, c in chunk])
        con.executemany("INSERT OR REPLACE INTO claim_vec VALUES(?,?,?)",
                        [(cid, a.embed_model, array.array("f", v.tolist()).tobytes()) for (cid, _), v in zip(chunk, m)])
        con.commit()
    log(f"embedded {len(rows)} claims")


def _claim_matrix(con):
    rows = con.execute("SELECT v.claim_id, c.unit_id, u.edition_id, v.vec FROM claim_vec v JOIN unit_claim c ON c.id=v.claim_id "
                       "JOIN unit u ON u.id=c.unit_id ORDER BY v.claim_id").fetchall()
    ids = [r[0] for r in rows]
    unit = [r[1] for r in rows]
    ed = np.array([r[2] for r in rows])
    m = np.array([array.array("f", r[3]) for r in rows], dtype="float32") if rows else np.zeros((0, 1), "float32")
    return ids, unit, ed, m


def cmd_pair(con, a, log=print):
    ids, unit, ed, m = _claim_matrix(con)
    have = {(s, d) for s, d in con.execute("SELECT src, dst FROM claim_pair")}
    new = 0
    sims = m @ m.T
    for i in range(len(ids)):
        row = sims[i].copy()
        row[ed == ed[i]] = -1.0                     # cross-book only
        for j in np.argsort(-row)[:a.k]:
            if row[j] < a.min:
                break
            s, d = sorted((ids[i], ids[int(j)]))
            if (s, d) in have:
                continue
            have.add((s, d))
            con.execute("INSERT INTO claim_pair(src, dst, cos) VALUES(?,?,?)", (s, d, float(row[j])))
            new += 1
    con.commit()
    log(f"pairs: {new} new candidates, {len(have)} total (k={a.k}, min cos {a.min})")


def cmd_judge(con, a, log=print):
    rows = con.execute(
        "SELECT p.src, p.dst, cs.claim, cd.claim, us.text, ud.text, us.ref, ud.ref, "
        "json_extract(es.data,'$.detected_title'), json_extract(ed.data,'$.detected_title') "
        "FROM claim_pair p JOIN unit_claim cs ON cs.id=p.src JOIN unit_claim cd ON cd.id=p.dst "
        "JOIN unit us ON us.id=cs.unit_id JOIN unit ud ON ud.id=cd.unit_id "
        "JOIN edition es ON es.id=us.edition_id JOIN edition ed ON ed.id=ud.edition_id "
        "WHERE p.rel IS NULL ORDER BY p.cos DESC" + (f" LIMIT {int(a.limit)}" if a.limit else "")).fetchall()
    t0, kept = time.time(), 0
    for n, (s, d, ca, cb, ta, tb, ra, rb, ba, bb) in enumerate(rows, 1):
        user = (f"Passage A ({ba}, {ra}):\n{ta[:1500]}\n\nClaim A: {ca}\n\n"
                f"Passage B ({bb}, {rb}):\n{tb[:1500]}\n\nClaim B: {cb}")
        body = {"model": a.model, "stream": False, "think": False, "format": JUDGE_SCHEMA, "options": {"temperature": 0},
                "messages": [{"role": "system", "content": JUDGE_SYSTEM}, {"role": "user", "content": user}]}
        try:
            out = json.loads(_post(f"{a.ollama}/api/chat", body)["message"]["content"])
        except Exception as ex:
            log(f"  pair {s}-{d}: {ex}")
            continue
        rel = out.get("relation", "none")
        kept += rel != "none"
        con.execute("UPDATE claim_pair SET rel=?, reason=?, confidence=?, model=?, created=? WHERE src=? AND dst=?",
                    (rel, out.get("reason", ""), float(out.get("confidence", 0) or 0), a.model, time.time(), s, d))
        if n % 25 == 0:
            con.commit()
            log(f"  judged {n}/{len(rows)}, {kept} edges, {(time.time() - t0) / n:.1f}s per pair")
    con.commit()
    log(f"judge: {len(rows)} pairs, {kept} edges, {time.time() - t0:.0f}s")


def edges_for_unit(con, uid: str) -> list[dict]:
    """Typed cross-book edges touching a unit, for the explorer: each with the other passage and both claims."""
    try:
        rows = con.execute(
            "SELECT p.src, p.dst, p.rel, p.reason, p.confidence, cs.unit_id, cd.unit_id, cs.claim, cd.claim "
            "FROM claim_pair p JOIN unit_claim cs ON cs.id=p.src JOIN unit_claim cd ON cd.id=p.dst "
            "WHERE p.rel IS NOT NULL AND p.rel!='none' AND (cs.unit_id=? OR cd.unit_id=?) ORDER BY p.confidence DESC",
            (uid, uid)).fetchall()
    except sqlite3.OperationalError:
        return []
    out = []
    for s, d, rel, reason, conf, us, ud, cs, cd in rows:
        here_is_src = us == uid
        other = ud if here_is_src else us
        if rel == "src_exemplifies_dst":
            rel = "example of" if here_is_src else "illustrated by"
        elif rel == "dst_exemplifies_src":
            rel = "illustrated by" if here_is_src else "example of"
        else:
            rel = rel.replace("_", " ")
        ed, ref, snip = con.execute("SELECT edition_id, ref, substr(text,1,220) FROM unit WHERE id=?", (other,)).fetchone()
        out.append({"rel": rel, "reason": reason, "confidence": conf, "claim": cs if here_is_src else cd,
                    "other_claim": cd if here_is_src else cs, "id": other, "edition": ed, "ref": ref, "snippet": snip})
    return out


def cmd_sample(con, a, log=print):
    rows = con.execute(
        "SELECT p.src, p.dst, p.rel, p.reason, p.confidence, p.cos, cs.claim, cd.claim, us.ref, ud.ref, "
        "json_extract(es.data,'$.detected_title'), json_extract(ed.data,'$.detected_title'), cs.quote, cd.quote "
        "FROM claim_pair p JOIN unit_claim cs ON cs.id=p.src JOIN unit_claim cd ON cd.id=p.dst "
        "JOIN unit us ON us.id=cs.unit_id JOIN unit ud ON ud.id=cd.unit_id "
        "JOIN edition es ON es.id=us.edition_id JOIN edition ed ON ed.id=ud.edition_id "
        "WHERE p.rel IS NOT NULL AND p.rel!='none'").fetchall()
    random.Random(a.seed).shuffle(rows)
    lines = [f"# Edge sample ({min(a.n, len(rows))} of {len(rows)} edges)\n",
             "Mark each line right/wrong. An edge is right if the relation holds between what the two passages say.\n"]
    for i, (s, d, rel, reason, conf, cos, ca, cb, ra, rb, ba, bb, qa, qb) in enumerate(rows[:a.n], 1):
        lines.append(f"## {i}. {rel}  (conf {conf:.2f}, cos {cos:.2f})  pair {s}-{d}\n"
                     f"- A [{ba}, {ra}]: {ca}\n  > {qa}\n- B [{bb}, {rb}]: {cb}\n  > {qb}\n- reason: {reason}\n- verdict: \n")
    text = "\n".join(lines)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
        log(f"wrote {a.out}")
    else:
        print(text)


def cmd_stats(con, a, log=print):
    log("units with claims:", con.execute("SELECT count(*), sum(n) FROM claim_done").fetchone())
    log("claims pinned:", con.execute("SELECT sum(start>=0), count(*) FROM unit_claim").fetchone())
    log("pairs by relation:", con.execute("SELECT coalesce(rel,'(unjudged)'), count(*) FROM claim_pair GROUP BY rel ORDER BY 2 DESC").fetchall())
    log("edges per book pair:", con.execute(
        "SELECT us.edition_id, ud.edition_id, count(*) FROM claim_pair p JOIN unit_claim cs ON cs.id=p.src "
        "JOIN unit_claim cd ON cd.id=p.dst JOIN unit us ON us.id=cs.unit_id JOIN unit ud ON ud.id=cd.unit_id "
        "WHERE p.rel IS NOT NULL AND p.rel!='none' GROUP BY 1,2 ORDER BY 3 DESC LIMIT 12").fetchall())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["claims", "embed", "pair", "judge", "sample", "stats"])
    ap.add_argument("--db", required=True)
    ap.add_argument("--ollama", default="http://localhost:11434")
    ap.add_argument("--model", default="gemma4:12b")
    ap.add_argument("--embed-model", default="qwen3-embedding:4b")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--min", type=float, default=0.6)
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    from . import live
    a.model = live.model_for(a.db, "edges" if a.cmd == "judge" else "claims", a.model)
    a.embed_model = live.model_for(a.db, "vectors", a.embed_model)
    con = sqlite3.connect(a.db)
    con.executescript(SCHEMA_SQL)
    {"claims": cmd_claims, "embed": cmd_embed, "pair": cmd_pair, "judge": cmd_judge, "sample": cmd_sample,
     "stats": cmd_stats}[a.cmd](con, a)


if __name__ == "__main__":
    main()
