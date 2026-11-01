"""S1: per-page lines with geometry and font, overprint removal, OCR/image flags."""
from __future__ import annotations
import pymupdf

from .model import Line
from .textnorm import display


def _near(a: Line, b: Line, tol: float = 3.0) -> bool:
    return abs(a.x0 - b.x0) <= tol and abs(a.y0 - b.y0) <= tol and a.text == b.text


def run(doc: pymupdf.Document) -> tuple[list[Line], dict]:
    lines: list[Line] = []
    stats = {"pages": doc.page_count, "image_only_pages": [], "image_pages": 0, "overprint_dropped": 0}
    for pno, page in enumerate(doc, start=1):
        d = page.get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT)
        H, W = page.rect.height, page.rect.width
        page_lines: list[Line] = []
        for bno, block in enumerate(d["blocks"]):
            for l in block.get("lines", []):
                spans, seen = [], []
                for s in l["spans"]:
                    key = (s["text"], round(s["bbox"][0]), round(s["bbox"][1]))
                    if s["text"].strip() and key in seen:   # duplicated span inside one line
                        stats["overprint_dropped"] += 1
                        continue
                    seen.append(key)
                    spans.append(s)
                text = display("".join(s["text"] for s in spans)).strip()
                if not text:
                    continue
                x0, y0, x1, y1 = l["bbox"]
                ln = Line(pno, bno, x0, y0, x1, y1, text,
                          max(s["size"] for s in spans), any(s["flags"] & 16 for s in spans), H, W)
                if any(_near(ln, o) for o in page_lines[-12:]):     # overprinted bold/shadow copies
                    stats["overprint_dropped"] += 1
                    continue
                page_lines.append(ln)
        has_images = bool(page.get_images())
        stats["image_pages"] += has_images
        if has_images and sum(len(l.text) for l in page_lines) < 50:
            stats["image_only_pages"].append(pno)
        lines.extend(page_lines)
    return lines, stats
