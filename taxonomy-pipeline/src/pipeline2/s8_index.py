"""S8: FTS5 index (porter stemming, spelling-normalized column) and optional embeddings."""
from __future__ import annotations
import array

from .models import Embedder
from .textnorm import search_copy


def build_fts(con, edition_id: str) -> int:
    rows = con.execute("SELECT u.id, u.text, d.label FROM unit u JOIN division d "
                       "ON d.edition_id=u.edition_id AND d.id=u.division_id WHERE u.edition_id=?", (edition_id,)).fetchall()
    con.execute("DELETE FROM unit_fts WHERE unit_id IN (SELECT id FROM unit WHERE edition_id=?)", (edition_id,))
    qs = dict(con.execute("SELECT unit_id, group_concat(question, ' ') FROM unit_question GROUP BY unit_id").fetchall())
    con.executemany("INSERT INTO unit_fts(unit_id, body, search, questions) VALUES(?,?,?,?)",
                    [(uid, text, search_copy(f"{label} {text}"), qs.get(uid, "")) for uid, text, label in rows])
    con.commit()
    return len(rows)


def build_vectors(con, emb: Embedder, edition_id: str | None = None, log=print) -> int:
    if not emb.enabled:
        return 0
    q = "SELECT id, text FROM unit WHERE id NOT IN (SELECT unit_id FROM unit_vec WHERE kind='unit' AND model=?)"
    args = [emb.cfg.model]
    if edition_id:
        q += " AND edition_id=?"
        args.append(edition_id)
    rows = con.execute(q, args).fetchall()
    for i in range(0, len(rows), emb.cfg.batch):
        chunk = rows[i:i + emb.cfg.batch]
        vecs = emb.embed([t[:6000] for _, t in chunk])
        con.executemany("INSERT OR REPLACE INTO unit_vec VALUES(?,?,?,?,?)",
                        [(uid, "unit", emb.cfg.model, len(v), array.array("f", v).tobytes()) for (uid, _), v in zip(chunk, vecs)])
        con.commit()
        log(f"  embedded {min(i + emb.cfg.batch, len(rows))}/{len(rows)}")
    qrows = con.execute("SELECT rowid, unit_id, question FROM unit_question WHERE rowid NOT IN "
                        "(SELECT CAST(substr(unit_id, 3) AS INT) FROM unit_vec WHERE kind='q' AND model=?)",
                        (emb.cfg.model,)).fetchall()
    for i in range(0, len(qrows), emb.cfg.batch):
        chunk = qrows[i:i + emb.cfg.batch]
        vecs = emb.embed([q for _, _, q in chunk])
        con.executemany("INSERT OR REPLACE INTO unit_vec VALUES(?,?,?,?,?)",
                        [(f"q:{rid}", "q", emb.cfg.model, len(v), array.array("f", v).tobytes()) for (rid, _, _), v in zip(chunk, vecs)])
        con.commit()
    return len(rows)
