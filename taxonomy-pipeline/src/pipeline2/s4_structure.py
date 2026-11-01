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

_KINDS = r"BOOK|PART|CHAPTER|CHAP\.?|ACT|SCENE|LETTER|ESSAY|SECTION|DISCOURSE|LECTURE|TREATISE"
_NUMS = r"[IVXLC]+|\d+|ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN"
_ORD = {"FIRST": "1", "SECOND": "2", "THIRD": "3", "FOURTH": "4", "FIFTH": "5", "SIXTH": "6", "SEVENTH": "7",
        "EIGHTH": "8", "NINTH": "9", "TENTH": "10"}
_DIV = re.compile(r"^(?P<kind>" + _KINDS + r")\s+(?P<num>" + _NUMS + r")\b", re.I)
_DIV_ORD = re.compile(r"^(?P<ord>" + "|".join(_ORD) + r")\s+(?P<kind>" + _KINDS + r")\b", re.I)
_PAIRS = re.compile(r"\b(" + _KINDS + r")\s+(" + _NUMS + r")\b", re.I)
_SENTENCE_LIKE = re.compile(r"[a-z][,;:]?$|[a-z][.?!]['\"\u2019\u201d]?\s*$")


def _canon(label: str) -> str:
    """'First Essay' -> 'Essay 1' so one pattern serves both orders."""
    m = _DIV_ORD.match(label)
    return f"{m.group('kind')} {_ORD[m.group('ord').upper()]}{label[m.end():]}" if m else label
_APPARATUS = re.compile(
    r"^(INTRODUCTION|PREFACE|FOREWORD|TRANSLATOR|EDITOR|NOTES?\b|ENDNOTES|BIBLIOGRAPHY|INDEX\b|CONTENTS|SUM[AÁ]RIO|"
    r"ACKNOWLEDG|ABOUT THE|GLOSSARY|CHRONOLOGY|FURTHER READING|HOW TO SHARE|FREE EBOOKS)", re.I)
_PREFACE = re.compile(r"^PREFACE\b", re.I)
_SPINE = re.compile(r"^(PART|BOOK)\s+[IVXLC\d]+\b", re.I)
_THE_END = re.compile(r"^(THE END|FINIS|END OF THE PROJECT GUTENBERG)\b", re.I)
_LEVEL = {"part": 1, "book": 1, "act": 1, "treatise": 1, "chapter": 2, "chap": 2, "chap.": 2, "letter": 2,
          "essay": 2, "discourse": 2, "lecture": 2, "scene": 3, "section": 3}


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
        t = _canon(p.text.strip())
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


def _from_generic(paras: list[Para]) -> list[tuple[int, int, str]]:
    """Books whose headings carry no 'Chapter N': every short heading paragraph is a division (Siddhartha's
    'THE SON OF THE BRAHMAN', the Manifesto's 'Bourgeois and Proletarians'). Stacked heading lines within
    150 chars (a title over a subtitle) merge into one label; a heading followed by under 800 chars of text
    is a title-page line, not a division."""
    heads = [p for p in paras if p.heading and 3 <= len(p.text.strip()) <= 80 and p.text.strip()[:1].isupper()
             and not _SENTENCE_LIKE.search(p.text.strip()) and not re.fullmatch(r"[\W\d]+", p.text.strip())]
    merged: list[list] = []
    for p in heads:
        if merged and p.start - merged[-1][1] < 150:
            merged[-1][1] = p.end
            merged[-1][2] += " " + p.text.strip()
        else:
            merged.append([p.start, p.end, p.text.strip()])
    out = []
    for i, (start, end, label) in enumerate(merged):
        nxt = merged[i + 1][0] if i + 1 < len(merged) else None
        if nxt is not None and nxt - start < 800:
            continue
        out.append((start, 2, label[:120]))
    return out


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
    """All (kind, number) pairs in a label: 'Part I, Chapter IV, ...' -> (('part', 1), ('chapter', 4))."""
    lab = _canon(match(label))
    if not _DIV.match(lab):
        return None
    pairs = tuple(("chapter" if k.lower().rstrip(".") == "chap" else k.lower().rstrip("."), _num(n)) for k, n in _PAIRS.findall(lab))
    return pairs or None


def _span(heads, i, n):
    return (heads[i + 1][0] if i + 1 < len(heads) else n) - heads[i][0]


def run(doc: pymupdf.Document, text: str, paras: list[Para]) -> list[Division]:
    heads = _from_outline(doc, text, paras) or _from_headings(paras)
    if sum(1 for h in heads if _DIV.match(_canon(h[2])) or _SPINE.match(h[2])) < 3:
        # no numbered spine: fall back to every heading paragraph, keeping any apparatus heads already found
        generic = _from_generic(paras)
        if len(generic) >= 2:
            starts = {h[0] for h in generic}
            heads = generic + [h for h in heads if h[0] not in starts and all(abs(h[0] - s) > 150 for s in starts)]
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
    if not heads:
        # no headings at all (Gracian's maxims): the whole text is the book, not front matter
        return [Division("d000", 1, "(body)", 0, len(text), "primary", 1, paras[0].page_start if paras else 1)]
    first_start = heads[0][0]
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
    # An 'Introduction' or 'Preface' that runs for a quarter of the book with no spine after it is the book
    # itself under an editor's first heading (Varieties, Frankenstein): primary, not apparatus.
    for d in divs:
        if d.zone == "apparatus" and d.end - d.start > 0.25 * len(text) and not _BACKISH.match(match(d.label)) \
                and not any(x.zone == "primary" and x.start >= d.end for x in divs):
            d.zone = "primary"
    for d in divs:
        d.page = page_of(d.start)
    return divs
