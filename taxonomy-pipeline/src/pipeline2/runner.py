"""Run S0-S6 + S8 (FTS) for one PDF and save everything to the SQLite store."""
from __future__ import annotations
import time
from pathlib import Path

import pymupdf

from . import s0_identity, s1_spans, s2_roles, s3_text, s4_structure, s6_units, s8_index
from .store import save_edition


def ingest(con, pdf: Path, edition_id: str | None = None, catalog_title: str = "", catalog_author: str = "") -> dict:
    t0 = time.time()
    edition_id = edition_id or pdf.stem
    ed = s0_identity.run(pdf, edition_id, catalog_title, catalog_author)
    doc = pymupdf.open(pdf)
    lines, s1 = s1_spans.run(doc)
    s2 = s2_roles.run(lines)
    text, paras, omap = s3_text.run(lines)
    divs = s4_structure.run(doc, text, paras)
    units = s6_units.run(edition_id, text, paras, divs)
    ed.image_only_pages = s1["image_only_pages"]
    ed.ocr_pages = s1["image_pages"]
    stats = {"s1": {k: v for k, v in s1.items() if k != "image_only_pages"}, "s2": s2,
             "paragraphs": len(paras), "divisions": len(divs), "units": len(units),
             "zones": {z: sum(1 for u in units if u.zone == z) for z in {u.zone for u in units}},
             "commentary_units": sum(1 for u in units if u.voice == "commentary"),
             "median_unit_words": sorted(u.words for u in units)[len(units) // 2] if units else 0,
             "seconds": round(time.time() - t0, 1)}
    save_edition(con, ed, text, omap, stats, divs, units)
    s8_index.build_fts(con, edition_id)
    return {"edition": ed, "stats": stats}
