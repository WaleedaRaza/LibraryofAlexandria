"""S4: divisions and zones.

Sources, best first: the PDF outline (when it has 3+ entries), then heading paragraphs that
look like divisions. A run of 5+ division headings packed into a few hundred characters is a
contents list, not the book. Zones: front (before the first division), apparatus
(introductions, prefaces, notes, ...), primary, back (after 'The End' or back-matter headings),
contents.
"""
from __future__ import annotations
import re

import pymupdf

from .model import Division, Para
from .textnorm import match

_DIV = re.compile(
    r"^(?P<kind>BOOK|PART|CHAPTER|CHAP\.?|ACT|SCENE|LETTER|ESSAY|SECTION)\s+(?P<num>[IVXLC]+|\d+|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN)\b",
    re.I)
_APPARATUS = re.compile(
    r"^(INTRODUCTION|PREFACE|FOREWORD|TRANSLATOR|EDITOR|NOTES?\b|ENDNOTES|BIBLIOGRAPHY|INDEX\b|CONTENTS|SUM[AÁ]RIO|"
    r"ACKNOWLEDG|ABOUT THE|GLOSSARY|CHRONOLOGY|FURTHER READING|HOW TO SHARE|FREE EBOOKS)", re.I)
_PREFACE = re.compile(r"^PREFACE\b", re.I)
_SPINE = re.compile(r"^(PART|BOOK)\s+[IVXLC\d]+\b", re.I)
_THE_END = re.compile(r"^(THE END|FINIS|END OF THE PROJECT GUTENBERG)\b", re.I)
_LEVEL = {"part": 1, "book": 1, "act": 1, "chapter": 2, "chap": 2, "chap.": 2, "letter": 2, "essay": 2,
          "scene": 3, "section": 3}


def _from_outline(doc: pymupdf.Document, text: str, paras: list[Para]) -> list[tuple[int, int, str]]:
    toc = doc.get_toc()
    if len(toc) < 3:
        return []
    found = []
    for level, title, page in toc:
        cands = [p for p in paras if p.page_start >= page - 1 and p.page_start <= page + 1]
        t = match(title).lower()
        hit = next((p for p in cands if match(p.text).lower().startswith(t[:30])), None)
        start = hit.start if hit else next((p.start for p in paras if p.page_start >= page), len(text))
        found.append((start, level, title.strip()))
    return found


def _from_headings(paras: list[Para]) -> list[tuple[int, int, str]]:
    found = []
    for i, p in enumerate(paras):
        t = p.text.strip()
        if not p.heading or len(t) > 120:
            continue
        m = _DIV.match(t)
        if m:
            label = t
            # 'Chapter 2' followed by a title heading: join them
            if i + 1 < len(paras) and paras[i + 1].heading and len(paras[i + 1].text) < 80 and not _DIV.match(paras[i + 1].text) \
                    and not _PREFACE.match(paras[i + 1].text.strip()):
                label = f"{t} {paras[i + 1].text.strip()}"
            found.append((p.start, _LEVEL.get(m.group("kind").lower(), 2), label))
        elif _APPARATUS.match(t) or _THE_END.match(t):
            # 'PART II. ...' then 'Preface': the author's preface to that part belongs to the part; a new
            # division here would swallow the whole part under the label 'Preface' (Spinoza, Ethics)
            if found and _DIV.match(found[-1][2]) and _PREFACE.match(t) and p.start - found[-1][0] < 400:
                continue
            found.append((p.start, 1, t))
    return found


def _mark_contents(heads: list[tuple[int, int, str]]) -> set[int]:
    """Indexes of headings that sit inside a contents list (5+ headings within ~250 chars each)."""
    idx = set()
    run = [0]
    for i in range(1, len(heads)):
        if heads[i][0] - heads[i - 1][0] < 250:
            run.append(i)
        else:
            if len(run) >= 5:
                idx.update(run)
            run = [i]
    if len(run) >= 5:
        idx.update(run)
    return idx


_BACKISH = re.compile(r"^(NOTES?\b|ENDNOTES|BIBLIOGRAPHY|INDEX\b|GLOSSARY|FURTHER READING|CHRONOLOGY)", re.I)


_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
_WORDNUM = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5, "SIX": 6, "SEVEN": 7, "EIGHT": 8, "NINE": 9, "TEN": 10}


def _num(tok: str) -> int:
    t = tok.upper()
    if t.isdigit():
        return int(t)
    if t in _WORDNUM:
        return _WORDNUM[t]
    total = 0
    for a, b in zip(t, t[1:] + " "):
        v = _ROMAN.get(a, 0)
        total += -v if _ROMAN.get(b, 0) > v else v
    return total


def _div_key(label: str):
    m = _DIV.match(match(label))
    if not m:
        return None
    kind = m.group("kind").lower().rstrip(".")
    return ("chapter" if kind == "chap" else kind, _num(m.group("num")))


def _span(heads, i, n):
    return (heads[i + 1][0] if i + 1 < len(heads) else n) - heads[i][0]


def run(doc: pymupdf.Document, text: str, paras: list[Para]) -> list[Division]:
    heads = _from_outline(doc, text, paras) or _from_headings(paras)
    heads.sort(key=lambda h: h[0])
    contents_idx = _mark_contents(heads)
    # the last heading of a contents run may be the real start of the book on the same page
    # (Spinoza: contents, then 'PART I.' and 80k characters of Part I): a long span is not a contents entry
    contents_idx = {i for i in contents_idx if _span(heads, i, len(text)) < 2000}
    # A division label that appears again later (BOOK VII in an introduction, chapter titles in a
    # contents list): the last copy is the real one. Earlier copies made of short lines are contents
    # entries; earlier copies inside running prose are mentions and stop being divisions.
    last = {}
    for i, h in enumerate(heads):
        k = _div_key(h[2])
        if k:
            last[k] = i
    drop = set()
    for i, h in enumerate(heads):
        k = _div_key(h[2])
        if k and last[k] != i:
            end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
            words = sorted(len(p.text.split()) for p in paras if h[0] <= p.start < end and not p.heading) or [0]
            (contents_idx.add(i) if words[len(words) // 2] < 15 else drop.add(i))
    if drop:
        keep = [h for i, h in enumerate(heads) if i not in drop]
        remap = {}
        for i, h in enumerate(heads):
            if i not in drop:
                remap[i] = len(remap)
        contents_idx = {remap[i] for i in contents_idx if i in remap}
        heads = keep
    # pages carrying 6+ headings are contents pages
    page_of = lambda off: next((p.page_start for p in paras if p.start >= off), 0)
    per_page = {}
    for i, h in enumerate(heads):
        per_page.setdefault(page_of(h[0]), []).append(i)
    for idxs in per_page.values():
        if len(idxs) >= 6:
            contents_idx.update(i for i in idxs if _span(heads, i, len(text)) < 600)

    divs: list[Division] = []
    first_start = heads[0][0] if heads else len(text)
    if first_start > 0:
        divs.append(Division("d000", 0, "(front)", 0, first_start, "front"))
    zone = "primary"
    seen_spine = False
    ordinals: dict[int, int] = {}
    for i, (start, level, label) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(text)
        lab = match(label)
        if i in contents_idx:
            z = "contents"
        elif _THE_END.match(lab):
            zone = "back"
            z = "back"
        elif zone == "back":
            z = "back"
        elif _APPARATUS.match(lab):
            # before the book proper: editor's material; after it: the author's own preface, or back matter
            z = "apparatus" if not seen_spine else ("back" if _BACKISH.match(lab) else "primary")
        elif _DIV.match(lab) and re.search(r"\bINTRODUCTION\b", lab, re.I):
            z = "apparatus"            # 'Chapter 1 Introduction' in Giles' Art of War
        else:
            z = "primary"
            if _DIV.match(lab) or _SPINE.match(lab):
                seen_spine = True
        d = Division(f"d{i + 1:03}", level, label[:160], start, end, z)
        if z == "primary":
            ordinals[level] = ordinals.get(level, 0) + 1
            for deeper in [k for k in ordinals if k > level]:
                ordinals[deeper] = 0
            d.ordinal = ordinals[level]
        divs.append(d)
    for d in divs:
        d.page = page_of(d.start)
    return divs
