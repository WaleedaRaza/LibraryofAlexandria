"""S2: label each line: furniture (running header/footer), pagenum, heading, note, body."""
from __future__ import annotations
import re
from collections import Counter, defaultdict
from statistics import median

from .model import Line

_PAGENUM = re.compile(r"^\W*(\d{1,4}|[ivxlcdm]{1,7})\W*$", re.I)
_SPINE_LINE = re.compile(r"^(PART|Part|BOOK|Book|CHAPTER|Chapter|ACT|Act)\s+([IVXLC]+|\d+)\b")
_SPINE_TITLE = re.compile(r"^(PART|BOOK)\s+[IVXLC]+[.:]\s+[A-Z][^.]*$")   # 'PART II. On The Nature Of The Mind'
_SENTENCE_END = re.compile(r"[a-z][.?!]['\"\u2019\u201d]?$")   # 'certainly not.' is dialogue, not a running head
_URL = re.compile(r"^(https?://|www\.)\S+$", re.I)
_HEAD = re.compile(
    r"^((FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH|EIGHTH|NINTH|TENTH)\s+)?"
    r"(BOOK|PART|CHAPTER|CHAP\.?|ACT|SCENE|SECTION|LETTER|ESSAY|DISCOURSE|LECTURE|TREATISE|PROP\.|PROPOSITION|"
    r"DEFINITIONS?|AXIOMS?|POSTULATES?|APPENDIX|PREFACE|INTRODUCTION|FOREWORD|EPILOGUE|PROLOGUE|CONTENTS|NOTES)\b", re.I)
# a bold or numbered caps line alone in its block, with no sentence end: 'I. THE THREE METAMORPHOSES.'
_NUMBERED_CAPS = re.compile(r"^([IVXLC]+|\d{1,3})\.\s+[A-Z][A-Z' ,-]{3,}\.?$")


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
        distinct = len({l.text.strip().lower() for l in ls}) / len(ls)
        # 'Chapter I', 'Chapter II' ... each at the top of its first page share a key but are distinct heads
        if steady >= 0.8 and not _SENTENCE_END.search(k) and not (distinct > 0.6 and _HEAD.match(ls[0].text.strip())):
            furniture_keys.add(k)
    # Furniture anywhere on the page: the same short line on a quarter of the pages at a steady height
    # (a footer printed above the bottom band, e.g. 'http://www.idph.net' at 0.81 in the Republic),
    # or a bare URL repeated on 3+ pages.
    occ_any: dict[str, list[Line]] = defaultdict(list)
    for l in lines:
        if len(l.text) <= 60 and by_block[(l.page, l.block)] <= 3:
            occ_any[_key(l.text)].append(l)
    for k, ls in occ_any.items():
        pages = {l.page for l in ls}
        if len(pages) >= 3 and _URL.match(ls[0].text.strip()):
            furniture_keys.add(k)
            continue
        if len(pages) < max(10, n_pages // 4) or _SENTENCE_END.search(k):
            continue
        ys = [l.y0 / l.page_h for l in ls]
        m = median(ys)
        if sum(abs(y - m) < 0.02 for y in ys) / len(ys) >= 0.9:
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
                or (len(l.text) <= 90 and _SPINE_LINE.match(l.text) and by_block[(l.page, l.block)] <= 2) \
                or (len(l.text) <= 90 and _SPINE_TITLE.match(l.text.strip())) \
                or (len(l.text) <= 60 and by_block[(l.page, l.block)] == 1 and l.text[:1].isupper()
                    and not _SENTENCE_END.search(l.text.strip())
                    and (l.bold or _NUMBERED_CAPS.match(l.text.strip()))):
            l.role = "heading"
        elif l.size < bsize * 0.88 and rel > 0.70:
            l.role = "note"
        else:
            l.role = "body"
        counts[l.role] += 1
    return {"body_size": bsize, "roles": dict(counts), "furniture": sorted(furniture_keys)[:40]}
