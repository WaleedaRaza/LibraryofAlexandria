"""Local explorer for the pipeline database: shelf, book view, atlas, ask, gold.

    python -m src.pipeline2.cli explore --db data/p2.sqlite        # http://127.0.0.1:8765

Standard library HTTP server plus numpy; the page is plain HTML/JS in ./explorer (no CDN, runs offline).
Ask uses the configured embedder and reranker when they answer, and falls back to lexical routing when not.
Reads only, except `gold_candidate` rows written by "save as gold".
"""
from __future__ import annotations
import json
import re
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import numpy as np

from . import project2d
from .s9_route import ZONE_WEIGHT, bm25, dense, route

STATIC = Path(__file__).parent / "explorer"
GOLD_DEFAULT = Path(__file__).resolve().parents[3] / "eval" / "gold_v0.jsonl"
EXTRA_SCHEMA = project2d.SCHEMA + """
CREATE TABLE IF NOT EXISTS gold_candidate(id INTEGER PRIMARY KEY, question TEXT, unit_id TEXT, note TEXT, created REAL);
"""
_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}


class Explorer:
    def __init__(self, db: str, emb=None, rerank=None, vec_model: str = "qwen3-embedding:4b", gold: Path | None = None):
        self.db, self.emb, self.rerank, self.vec_model = db, emb, rerank, vec_model
        self.gold_path = gold or GOLD_DEFAULT
        self.local = threading.local()
        con = self.con()
        con.executescript(EXTRA_SCHEMA)
        self.ids, self.mat = project2d.unit_matrix(con, vec_model)
        self.row = {u: i for i, u in enumerate(self.ids)}
        self.ed_of = dict(con.execute("SELECT id, edition_id FROM unit").fetchall())
        self.gold = self._load_gold()

    def con(self) -> sqlite3.Connection:
        if not hasattr(self.local, "con"):
            self.local.con = sqlite3.connect(self.db)
        return self.local.con

    def _load_gold(self) -> list[dict]:
        p = Path(self.gold_path)
        if not p.exists():
            return []
        return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]

    # ---- data -------------------------------------------------------------------------------------
    def books(self) -> list[dict]:
        con = self.con()
        out = []
        for eid, data, n in con.execute("SELECT id, data, length(text) FROM edition ORDER BY id"):
            d = json.loads(data)
            title = d.get("detected_title") or eid
            if len(title) > 80:
                title = d.get("catalog_title") or eid
            zones = dict(con.execute("SELECT zone, sum(words) FROM unit WHERE edition_id=? GROUP BY zone", (eid,)))
            voices = con.execute("SELECT voice_name, count(*) FROM unit WHERE edition_id=? AND voice='commentary' "
                                 "GROUP BY 1 ORDER BY 2 DESC", (eid,)).fetchall()
            units, qs = con.execute("SELECT count(*), (SELECT count(*) FROM unit_question q JOIN unit u2 ON "
                                    "u2.id=q.unit_id WHERE u2.edition_id=?) FROM unit WHERE edition_id=?",
                                    (eid, eid)).fetchone()
            divs = con.execute("SELECT count(*) FROM division WHERE edition_id=? AND zone='primary'", (eid,)).fetchone()[0]
            out.append({"id": eid, "title": title, "chars": n, "pages": d.get("pages"), "ocr_pages": d.get("ocr_pages", 0),
                        "zones": zones, "units": units, "questions": qs, "primary_divisions": divs,
                        "commentators": voices[:8], "gold": sum(1 for g in self.gold for a in g["gold"] if a["book"] == eid),
                        "warnings": self._warnings(con, eid, d)})
        return out

    def _warnings(self, con, eid, d) -> list[str]:
        w = []
        labels = [r[0] for r in con.execute("SELECT label FROM division WHERE edition_id=? AND zone='primary'", (eid,))]
        dup = {l for l in labels if labels.count(l) > 1}
        if dup:
            w.append(f"repeated division labels: {', '.join(sorted(dup))[:80]}")
        furn = con.execute("SELECT count(*) FROM unit WHERE edition_id=? AND zone='primary' AND "
                           "(text LIKE '%idph.net%' OR text LIKE '%Planet eBook%')", (eid,)).fetchone()[0]
        if furn:
            w.append(f"{furn} primary units contain running-header text")
        if any(re.search(r"ebook|how to share", l, re.I) for l in labels):
            w.append("eBook boilerplate counted as primary")
        ed = con.execute("SELECT count(*) FROM unit WHERE edition_id=? AND voice='commentary' AND voice_name='editor'",
                         (eid,)).fetchone()[0]
        if ed > 20:
            w.append(f"{ed} commentary units without a named commentator")
        if len(d.get("detected_title", "")) > 80:
            w.append("detected title is boilerplate")
        return w

    def book(self, eid: str) -> dict:
        con = self.con()
        divs = [dict(zip(("id", "level", "label", "start", "end", "zone", "ordinal", "page"), r)) for r in con.execute(
            "SELECT id, level, label, start, end, zone, ordinal, page FROM division WHERE edition_id=? ORDER BY start", (eid,))]
        xy = dict(((u, (x, y)) for u, x, y in con.execute("SELECT unit_id, x, y FROM unit_xy WHERE model=?", (self.vec_model,))))
        units = []
        lab = self.labels()
        for r in con.execute("SELECT u.id, u.division_id, u.zone, u.voice, u.voice_name, u.ref, u.start, u.end, "
                             "u.page_start, u.page_end, u.words, (SELECT count(*) FROM unit_question q WHERE q.unit_id=u.id) "
                             "FROM unit u WHERE u.edition_id=? ORDER BY u.start", (eid,)):
            d = dict(zip(("id", "div", "zone", "voice", "voice_name", "ref", "start", "end", "p0", "p1", "words", "nq"), r))
            d["type"] = lab.get(d["id"], (None,))[0]
            units.append(d)
        gold = [g for g in self.gold if any(a["book"] == eid for a in g["gold"])]
        return {"id": eid, "divisions": divs, "units": units, "gold": gold, "has_xy": bool(xy)}

    def unit(self, uid: str) -> dict:
        con = self.con()
        r = con.execute("SELECT id, edition_id, division_id, zone, voice, voice_name, ref, start, end, page_start, page_end, "
                        "words, text FROM unit WHERE id=?", (uid,)).fetchone()
        if not r:
            return {}
        u = dict(zip(("id", "edition", "div", "zone", "voice", "voice_name", "ref", "start", "end", "p0", "p1", "words", "text"), r))
        u["questions"] = [q for (q,) in con.execute("SELECT question FROM unit_question WHERE unit_id=?", (uid,))]
        u["neighbours"] = self.neighbours(uid, 8)
        prev_next = con.execute("SELECT (SELECT id FROM unit WHERE edition_id=? AND start<? ORDER BY start DESC LIMIT 1), "
                                "(SELECT id FROM unit WHERE edition_id=? AND start>? ORDER BY start LIMIT 1)",
                                (u["edition"], u["start"], u["edition"], u["start"])).fetchone()
        u["prev"], u["next"] = prev_next
        return u

    def neighbours(self, uid: str, k: int = 8) -> list[dict]:
        """Nearest units in other books by the stored unit vectors: cross-book discovery with no graph."""
        i = self.row.get(uid)
        if i is None:
            return []
        sims = self.mat @ self.mat[i]
        own = self.ed_of[uid]
        out, con = [], self.con()
        for j in np.argsort(-sims):
            vid = self.ids[j]
            if self.ed_of.get(vid) == own:
                continue
            z, ref, text = con.execute("SELECT zone, ref, substr(text, 1, 220) FROM unit WHERE id=?", (vid,)).fetchone()
            if z != "primary":
                continue
            out.append({"id": vid, "edition": self.ed_of[vid], "sim": round(float(sims[j]), 3), "ref": ref, "snippet": text})
            if len(out) >= k:
                break
        return out

    def labels(self) -> dict:
        """unit_id -> (type, type2, evidence start, evidence end); empty before the labelling step has run."""
        try:
            return {u: (t, t2, s, e) for u, t, t2, s, e in
                    self.con().execute("SELECT unit_id, type, type2, start, end FROM unit_label")}
        except sqlite3.OperationalError:
            return {}

    def division_units(self, eid: str, div: str) -> list[dict]:
        rows = self.con().execute("SELECT id, zone, voice, voice_name, ref, page_start, page_end, text FROM unit "
                                  "WHERE edition_id=? AND division_id=? ORDER BY start", (eid, div)).fetchall()
        lab = self.labels()
        out = []
        for r in rows:
            d = dict(zip(("id", "zone", "voice", "voice_name", "ref", "p0", "p1", "text"), r))
            t, t2, s, e = lab.get(d["id"], (None, None, -1, -1))
            d.update(type=t, type2=t2, ev=[s, e] if s is not None and s >= 0 else None)
            out.append(d)
        return out

    def atlas(self) -> list[list]:
        return self.con().execute("SELECT x.unit_id, u.edition_id, round(x.x, 4), round(x.y, 4), u.zone, u.voice "
                                  "FROM unit_xy x JOIN unit u ON u.id=x.unit_id WHERE x.model=?", (self.vec_model,)).fetchall()

    def ask(self, q: str, k: int = 10, use_dense: bool = True, use_rerank: bool = True) -> dict:
        con, t0 = self.con(), time.time()
        mode, notes = ["bm25"], []
        lex = {u: i + 1 for i, (u, _) in enumerate(bm25(con, q))}
        den = {}
        emb = self.emb if (use_dense and self.emb is not None and self.emb.enabled) else None
        if emb is not None:
            try:
                den = {u: i + 1 for i, (u, _) in enumerate(dense(con, emb, q))}
                mode.append("dense")
            except Exception as e:                    # model server down: stay lexical
                notes.append(f"dense off: {type(e).__name__}")
                emb = None
        rr = self.rerank if (use_rerank and self.rerank is not None and self.rerank.enabled) else None
        hits = None
        if rr is not None:
            try:
                hits = route(con, q, k=k, emb=emb, rerank=rr)
                mode.append("rerank")
            except Exception as e:                    # reranker down, or an older route() without rerank
                notes.append(f"rerank off: {type(e).__name__}")
        if hits is None:
            hits = route(con, q, k=k, emb=emb)
        key = lambda s: re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
        gold = next((g for g in self.gold if key(g["question"]) == key(q)), None)
        return {"q": q, "mode": mode, "notes": notes, "ms": int((time.time() - t0) * 1000), "gold": gold,
                "hits": [{"id": h.unit_id, "edition": h.edition_id, "score": round(h.score, 4), "zone": h.zone,
                          "voice": h.voice, "voice_name": h.voice_name, "ref": h.ref, "p0": h.page_start, "p1": h.page_end,
                          "text": h.text[:1200], "bm25": lex.get(h.unit_id), "dense": den.get(h.unit_id)} for h in hits]}

    def save_gold(self, body: dict) -> dict:
        con = self.con()
        con.execute("INSERT INTO gold_candidate(question, unit_id, note, created) VALUES(?,?,?,?)",
                    (body.get("question", "")[:500], body.get("unit_id", ""), body.get("note", "")[:500], time.time()))
        con.commit()
        return {"saved": con.execute("SELECT count(*) FROM gold_candidate").fetchone()[0]}

    def status(self) -> dict:
        return {"db": str(self.db), "vec_model": self.vec_model, "vectors": len(self.ids),
                "dense": bool(self.emb and self.emb.enabled), "rerank": bool(self.rerank and self.rerank.enabled),
                "zone_weight": ZONE_WEIGHT}


def make_handler(ex: Explorer):
    class H(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):     # quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):
            u = urlparse(self.path)
            p, qs = unquote(u.path), parse_qs(u.query)
            arg = lambda k, d="": qs.get(k, [d])[0]
            try:
                if p == "/api/status":
                    return self._json(ex.status())
                if p == "/api/books":
                    return self._json(ex.books())
                if p.startswith("/api/book/"):
                    return self._json(ex.book(p[len("/api/book/"):]))
                if p.startswith("/api/unit/"):
                    return self._json(ex.unit(p[len("/api/unit/"):]))
                if p == "/api/division":
                    return self._json(ex.division_units(arg("book"), arg("div")))
                if p == "/api/atlas":
                    return self._json(ex.atlas())
                if p == "/api/ask":
                    return self._json(ex.ask(arg("q"), int(arg("k", "10")), arg("dense", "1") == "1", arg("rerank", "1") == "1"))
                name = "index.html" if p in ("/", "") else p.lstrip("/")
                f = (STATIC / name).resolve()
                if STATIC.resolve() in f.parents and f.is_file():
                    return self._send(200, f.read_bytes(), _TYPES.get(f.suffix, "application/octet-stream"))
                return self._json({"error": "not found"}, 404)
            except Exception as e:
                return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

        def do_POST(self):
            if urlparse(self.path).path != "/api/gold":
                return self._json({"error": "not found"}, 404)
            n = int(self.headers.get("Content-Length", "0") or 0)
            try:
                return self._json(ex.save_gold(json.loads(self.rfile.read(n) or b"{}")))
            except Exception as e:
                return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    return H


def serve(ex: Explorer, host: str = "127.0.0.1", port: int = 8765, log=print):
    srv = ThreadingHTTPServer((host, port), make_handler(ex))
    log(f"explorer on http://{host}:{port}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


def _from_config(path: str):
    """Embedder and reranker from config.yaml `pipeline2:`, tolerating older models.py without a reranker."""
    import yaml
    from . import models
    p = Path(path)
    cfg = (yaml.safe_load(p.read_text()) or {}).get("pipeline2", {}) if p.exists() else {}
    emb = models.Embedder(models.EmbedConfig(**cfg.get("embed", {})))
    rr = None
    if hasattr(models, "Reranker") and cfg.get("rerank"):
        rr = models.Reranker(models.RerankConfig(**cfg["rerank"]))
    return (emb if emb.enabled else None), (rr if rr is not None and rr.enabled else None), emb.cfg.model


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="python -m src.pipeline2.explore", description="LibXNDR local explorer")
    ap.add_argument("--db", required=True)
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--model", default=None, help="embedding model for atlas and neighbours")
    ap.add_argument("--gold", default=None)
    ap.add_argument("--reproject", action="store_true", help="recompute atlas coordinates")
    a = ap.parse_args(argv)
    emb, rr, cfg_model = _from_config(a.config)
    model = a.model or cfg_model
    con = sqlite3.connect(a.db)
    con.executescript(project2d.SCHEMA)
    if a.reproject or not con.execute("SELECT 1 FROM unit_xy WHERE model=? LIMIT 1", (model,)).fetchone():
        print(f"computing atlas coordinates for {model} (one time, a few minutes)...")
        project2d.build(con, model)
    con.close()
    serve(Explorer(a.db, emb, rr, model, Path(a.gold) if a.gold else None), a.host, a.port)


if __name__ == "__main__":
    main()
