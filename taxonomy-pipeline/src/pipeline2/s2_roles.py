"""S2: label each line: furniture (running header/footer), pagenum, heading, note, body."""
from __future__ import annotations
import re
from collections import Counter, defaultdict
from statistics import median

from .model import Line

_PAGENUM = re.compile(r"^\W*(\d{1,4}|[ivxlcdm]{1,7})\W*$", re.I)
_SPINE_LINE = re.compile(r"^(PART|Part|BOOK|Book|CHAPTER|Chapter|ACT|Act)\s+([IVXLC]+|\d+)\b")
_HEAD = re.compile(
    r"^(BOOK|PART|CHAPTER|CHAP\.?|ACT|SCENE|SECTION|LETTER|ESSAY|PROP\.|PROPOSITION|DEFINITIONS?|AXIOMS?|"
    r"POSTULATES?|APPENDIX|PREFACE|INTRODUCTION|FOREWORD|EPILOGUE|PROLOGUE|CONTENTS|NOTES)\b", re.I)


def _key(text: str) -> str:
    t = re.sub(r"\d+", "#", text.lower())
    t = re.sub(r"\b[ivxlc]+\b", "#", t)
    return re.sub(r"\s+", " ", t).strip()


def body_size(lines: list[Line]) -> float:
    c = Counter()
    for l in lines:
        c[round(l.size * 2) / 2] += len(l.text)
    return c.most_common(1)[0][0] if c else 10.0


def run(lines: list[Line]) -> dict:
    if not lines:
        return {"body_size": 0}
    bsize = body_size(lines)
    n_pages = max(l.page for l in lines)
    by_block = Counter((l.page, l.block) for l in lines)

    # Furniture: short text repeated at a consistent vertical position on several pages,
    # sitting in its own small block near the top or bottom.
    occ: dict[str, list[Line]] = defaultdict(list)
    for l in lines:
        rel = l.y0 / l.page_h
        if len(l.text) <= 80 and by_block[(l.page, l.block)] <= 3 and (rel < 0.16 or rel > 0.86):
            occ[_key(l.text)].append(l)
    furniture_keys = set()
    for k, ls in occ.items():
        pages = {l.page for l in ls}
        if len(pages) < 3:
            continue
        ys = [l.y0 / l.page_h for l in ls]
        m = median(ys)
        steady = sum(abs(y - m) < 0.03 for y in ys) / len(ys)
        if steady >= 0.8:
            furniture_keys.add(k)

    counts = Counter()
    for l in lines:
        rel = l.y0 / l.page_h
        edge = rel < 0.16 or rel > 0.86
        if _key(l.text) in furniture_keys:
            l.role = "furniture"
        elif edge and _PAGENUM.match(l.text) and by_block[(l.page, l.block)] <= 3:
            l.role = "pagenum"
        elif (len(l.text) < 70 and l.text[:1].isupper()
              and (l.size >= bsize * 1.18 or (_HEAD.match(l.text) and (l.text.isupper() or len(l.text) < 40)))) \
                or (len(l.text) <= 90 and _SPINE_LINE.match(l.text) and by_block[(l.page, l.block)] <= 2):
            l.role = "heading"
        elif l.size < bsize * 0.88 and rel > 0.70:
            l.role = "note"
        else:
            l.role = "body"
        counts[l.role] += 1
    return {"body_size": bsize, "roles": dict(counts), "furniture": sorted(furniture_keys)[:40]}
