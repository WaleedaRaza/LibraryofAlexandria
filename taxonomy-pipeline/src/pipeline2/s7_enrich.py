"""S7: per-unit questions and gist from a local model (optional; needs gen.provider != none).

The model only writes questions a reader might ask that the unit answers. Questions are indexed
for retrieval; they are never shown as the book's words.
"""
from __future__ import annotations
from .models import Generator

SCHEMA = {
    "type": "object",
    "properties": {
        "gist": {"type": "string"},
        "questions": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 5},
    },
    "required": ["gist", "questions"],
}
SYSTEM = ("You index passages of books so readers can find them. Reply with JSON only. "
          "Write questions in plain modern English, the way a curious reader would ask them, "
          "that this passage directly answers. Do not quote the passage. Do not invent content.")


def run(con, gen: Generator, edition_id: str | None = None, limit: int | None = None, log=print) -> int:
    q = "SELECT u.id, u.text, u.ref, u.voice, u.voice_name, json_extract(e.data,'$.detected_title') " \
        "FROM unit u JOIN edition e ON e.id=u.edition_id " \
        "WHERE u.zone='primary' AND u.id NOT IN (SELECT unit_id FROM unit_question WHERE model=?)"
    args = [gen.cfg.model]
    if edition_id:
        q += " AND u.edition_id=?"
        args.append(edition_id)
    rows = con.execute(q + (f" LIMIT {int(limit)}" if limit else ""), args).fetchall()
    for n, (uid, text, ref, voice, vname, title) in enumerate(rows, 1):
        speaker = f" (speaker: {vname}, a commentator)" if voice == "commentary" else ""
        out = gen.json(SYSTEM, f"Book: {title}\nLocation: {ref}{speaker}\n\nPassage:\n{text[:4000]}", SCHEMA)
        qs = [s.strip() for s in out.get("questions", []) if isinstance(s, str) and s.strip()][:5]
        con.executemany("INSERT INTO unit_question VALUES(?,?,?)", [(uid, s, gen.cfg.model) for s in qs])
        con.execute("UPDATE unit_fts SET questions=? WHERE unit_id=?", (" ".join(qs), uid))
        if n % 25 == 0:
            con.commit()
            log(f"  enriched {n}/{len(rows)}")
    con.commit()
    return len(rows)
