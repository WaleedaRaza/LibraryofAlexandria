"""S6 (+ S5 voice): cut divisions into logical units.

A new unit starts at: a numbered section ("17. Remember that..."), a geometric-order marker
(PROP. / Proof / Note / Corollary / Definitions / Axioms / roman-numbered definitions), or a change
of voice (bracketed commentary in annotated editions). Otherwise paragraphs are grouped to
~150-450 words and split above ~700 words at sentence ends. Units never cross divisions.
"""
from __future__ import annotations
import re

from .model import Division, Para, Unit

_NUMBERED = re.compile(r"^(\d{1,3})\.\s+\S")
_NUM_ONLY = re.compile(r"^(\d{1,3})\.$")
_GEOM = re.compile(r"^(PROP\.|PROPOSITION|Proof|Note|Corollary|Scholium|Lemma|Explanation|DEFINITIONS?|AXIOMS?|"
                   r"POSTULATES?|Def\.|[IVXL]{1,6}\.\s)")
_COMMENT = re.compile(r"^\[\s*(?:As\s+)?(?P<name>[A-Z][\w‘’'\-]+(?:\s+[A-Z][\w‘’'\-]+)?)\s+"
                      r"(?:says|remarks|quotes|adds|thinks|explains|observes|tells|notes|points|writes|comments|has)")
_SENT = re.compile(r"(?<=[.!?\"'\u201d\u2019])\s+(?=[A-Z\"'\u201c\u2018])")

MIN_WORDS, TARGET_WORDS, MAX_WORDS = 150, 350, 700


def _words(s: str) -> int:
    return len(s.split())


def run(edition_id: str, text: str, paras: list[Para], divs: list[Division]) -> list[Unit]:
    units: list[Unit] = []

    def add(div: Division, group: list[Para], voice: str, name: str, ref: str):
        if not group:
            return
        start, end = group[0].start, group[-1].end
        body = text[start:end]
        if not body.strip():
            return
        pieces = [(start, end)]
        if _words(body) > MAX_WORDS:                       # split long runs at sentence ends
            pieces, cur = [], start
            acc = 0
            for m in _SENT.finditer(body):
                seg_words = _words(text[cur:start + m.start()])
                if seg_words >= TARGET_WORDS:
                    pieces.append((cur, start + m.start()))
                    cur = start + m.end()
            pieces.append((cur, end))
        for s, e in pieces:
            pg = [p for p in group if p.end > s and p.start < e]
            units.append(Unit(
                id=f"{edition_id}:{len(units) + 1:05}", edition_id=edition_id, division_id=div.id, zone=div.zone,
                voice=voice, voice_name=name, ref=ref, start=s, end=e,
                page_start=pg[0].page_start if pg else 0, page_end=pg[-1].page_end if pg else 0,
                text=text[s:e], words=_words(text[s:e])))

    for div in divs:
        dparas = [p for p in paras if p.start >= div.start and p.end <= div.end and not p.heading]
        group: list[Para] = []
        voice, name, ref = "author", "", div.label[:60]
        depth = 0                      # open '[' count carried across paragraphs
        pending_num = False
        for p in dparas:
            t = p.text.strip()
            if _NUM_ONLY.match(t) and depth == 0:          # "24." alone: starts the next unit
                add(div, group, voice, name, ref)
                group, voice, name = [p], "author", ""
                ref = f"{div.label[:40]} \u00a7{_NUM_ONLY.match(t).group(1)}"
                pending_num = True
                continue
            starts_comment = depth == 0 and t.startswith("[")
            ends_comment = depth == 0 and voice == "commentary" and not starts_comment
            new_number = depth == 0 and bool(_NUMBERED.match(t)) and not pending_num
            new_geom = depth == 0 and bool(_GEOM.match(t))
            if (starts_comment or ends_comment or new_number or new_geom) and group and not pending_num:
                add(div, group, voice, name, ref)
                group = []
            if starts_comment:
                m = _COMMENT.match(t)
                voice, name = "commentary", (m.group("name") if m else "editor")
            elif ends_comment:
                voice, name = "author", ""
            if new_number:
                ref = f"{div.label[:40]} \u00a7{_NUMBERED.match(t).group(1)}"
            elif new_geom:
                ref = f"{div.label[:40]} {t[:24]}"
            pending_num = False
            group.append(p)
            depth = max(0, depth + t.count("[") - t.count("]"))
            if voice == "author" and depth == 0 and sum(_words(x.text) for x in group) >= TARGET_WORDS \
                    and not _NUMBERED.match(group[0].text) and not _GEOM.match(group[0].text):
                add(div, group, voice, name, ref)
                group = []
        add(div, group, voice, name, ref)
    return units
