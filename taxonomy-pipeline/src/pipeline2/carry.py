"""Carry generated questions and vectors from an older database into a re-ingested one.

A parser fix changes only some units. Units whose (edition, text) is unchanged keep their questions
and every model's vectors, so only the changed units need `enrich` and `embed` again.

    python -m src.pipeline2.carry --old data/p2.sqlite --new data/p2_v1.sqlite
"""
from __future__ import annotations
import argparse
import sqlite3


def carry(old: sqlite3.Connection, new: sqlite3.Connection, log=print) -> dict:
    new_by_text = {(e, t): u for u, e, t in new.execute("SELECT id, edition_id, text FROM unit")}
    remap = {}
    for u, e, t in old.execute("SELECT id, edition_id, text FROM unit"):
        nu = new_by_text.get((e, t))
        if nu:
            remap[u] = nu
    q_rows = old.execute("SELECT rowid, unit_id, question, model FROM unit_question").fetchall()
    qmap = {}
    for rowid, u, q, m in q_rows:
        if u in remap:
            cur = new.execute("INSERT INTO unit_question(unit_id, question, model) VALUES(?,?,?)", (remap[u], q, m))
            qmap[rowid] = cur.lastrowid
    nvec = 0
    for uid, kind, model, dim, vec in old.execute("SELECT unit_id, kind, model, dim, vec FROM unit_vec"):
        if kind == "unit" and uid in remap:
            new.execute("INSERT OR REPLACE INTO unit_vec VALUES(?,?,?,?,?)", (remap[uid], kind, model, dim, vec))
            nvec += 1
        elif kind == "q" and int(uid[2:]) in qmap:
            new.execute("INSERT OR REPLACE INTO unit_vec VALUES(?,?,?,?,?)", (f"q:{qmap[int(uid[2:])]}", kind, model, dim, vec))
            nvec += 1
    qs = dict(new.execute("SELECT unit_id, group_concat(question, ' ') FROM unit_question GROUP BY unit_id").fetchall())
    new.executemany("UPDATE unit_fts SET questions=? WHERE unit_id=?", [(v, k) for k, v in qs.items()])
    new.commit()
    total = new.execute("SELECT count(*) FROM unit").fetchone()[0]
    res = {"units": total, "carried_units": len(remap), "questions": len(qmap), "vectors": nvec,
           "need_enrich": total - len({remap[u] for u in remap})}
    log(res)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    a = ap.parse_args()
    carry(sqlite3.connect(a.old), sqlite3.connect(a.new))


if __name__ == "__main__":
    main()
