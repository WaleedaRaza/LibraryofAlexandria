"""S9: route a question to units. BM25 (FTS5) + optional dense (unit and question vectors), RRF-fused,
with zone weighting so editors' introductions and contents pages do not outrank the book."""
from __future__ import annotations
import array
import math
import re
from dataclasses import dataclass

from .models import Embedder, Reranker
from .textnorm import search_copy

STOP = set("""a an the of to and or is are was were be been in on at for with by as it its this that these those
what which who whom whose how why when where do does did i me my we our you your he she they them his her their
should would could can may might must about say says said tell according there here than then so not no
""".split())
ZONE_WEIGHT = {"primary": 1.0, "apparatus": 0.35, "front": 0.25, "back": 0.25, "contents": 0.05}
RRF_K = 60


@dataclass
class Hit:
    unit_id: str
    edition_id: str
    score: float
    zone: str
    voice: str
    voice_name: str
    ref: str
    page_start: int
    page_end: int
    text: str


def _terms(q: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]+", search_copy(q).lower()) if w not in STOP and len(w) > 1]


def bm25(con, question: str, k: int = 100) -> list[tuple[str, float]]:
    terms = _terms(question)
    if not terms:
        return []
    expr = " OR ".join(f'"{t}"' for t in terms)
    rows = con.execute(
        "SELECT unit_id, bm25(unit_fts, 0.0, 1.0, 1.0, 0.6) AS s FROM unit_fts WHERE unit_fts MATCH ? ORDER BY s LIMIT ?",
        (f"{{body search questions}} : ({expr})", k)).fetchall()
    return [(uid, -s) for uid, s in rows]


_VEC_CACHE: dict = {}


def _load_vectors(con, model: str):
    if model not in _VEC_CACHE:
        import numpy as np
        rows = con.execute("SELECT v.unit_id, v.kind, v.vec, q.unit_id FROM unit_vec v LEFT JOIN unit_question q "
                           "ON v.kind='q' AND q.rowid = CAST(substr(v.unit_id, 3) AS INT) WHERE v.model=?", (model,)).fetchall()
        ids = [(qu if kind == "q" else uid) for uid, kind, _, qu in rows]
        mat = np.array([array.array("f", b) for _, _, b, _ in rows], dtype="float32") if rows else np.zeros((0, 1), "float32")
        if len(mat):
            mat /= np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9
        _VEC_CACHE[model] = (ids, mat)
    return _VEC_CACHE[model]


def dense(con, emb: Embedder, question: str, k: int = 100) -> list[tuple[str, float]]:
    import numpy as np
    ids, mat = _load_vectors(con, emb.cfg.model)
    if not len(ids):
        return []
    qv = np.array(emb.embed([question], query=True)[0], dtype="float32")
    qv /= np.linalg.norm(qv) + 1e-9
    sims = mat @ qv
    best: dict[str, float] = {}
    for i in np.argsort(-sims)[: k * 3]:
        uid = ids[i]
        if uid and uid not in best:
            best[uid] = float(sims[i])
        if len(best) >= k:
            break
    return list(best.items())


def route(con, question: str, k: int = 10, emb: Embedder | None = None, zones: dict | None = None,
          rerank: Reranker | None = None) -> list[Hit]:
    zw = zones or ZONE_WEIGHT
    lists = [bm25(con, question)]
    if emb is not None and emb.enabled:
        lists.append(dense(con, emb, question))
    fused: dict[str, float] = {}
    for lst in lists:
        for rank, (uid, _) in enumerate(lst):
            fused[uid] = fused.get(uid, 0.0) + 1.0 / (RRF_K + rank + 1)
    if not fused:
        return []
    meta = {r[0]: r for r in con.execute(
        f"SELECT id, edition_id, zone, voice, voice_name, ref, page_start, page_end, text FROM unit WHERE id IN "
        f"({','.join('?' * len(fused))})", list(fused))}
    hits = []
    for uid, s in fused.items():
        m = meta[uid]
        hits.append(Hit(uid, m[1], s * zw.get(m[2], 0.5), m[2], m[3], m[4], m[5], m[6], m[7], m[8]))
    hits.sort(key=lambda h: -h.score)
    if rerank is not None and rerank.enabled and hits:
        head, tail = hits[: rerank.cfg.top], hits[rerank.cfg.top:]
        for h, s in zip(head, rerank.scores(question, [f"{h.ref}\n{h.text}" for h in head])):
            h.score = s * zw.get(h.zone, 0.5)
        head.sort(key=lambda h: -h.score)
        hits = head + tail
    return hits[:k]


def rank_books(hits: list[Hit]) -> list[tuple[str, float]]:
    """Book score = best unit + half of the rest, so one exact passage beats many loose mentions."""
    by: dict[str, list[float]] = {}
    for h in hits:
        by.setdefault(h.edition_id, []).append(h.score)
    return sorted(((e, s[0] + 0.5 * sum(s[1:])) for e, s in ((e, sorted(v, reverse=True)) for e, v in by.items())),
                  key=lambda x: -x[1])
