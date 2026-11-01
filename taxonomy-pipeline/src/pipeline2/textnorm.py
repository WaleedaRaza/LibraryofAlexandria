"""Normalization shared by indexing, eval anchors and display."""
from __future__ import annotations
import re
import unicodedata

_PUNCT = {"’": "'", "‘": "'", "“": '"', "”": '"', "—": "-", "–": "-", "­": ""}


def display(s: str) -> str:
    """What we store and show: NFKC (ligatures -> letters), soft hyphens removed."""
    return unicodedata.normalize("NFKC", s).replace("­", "")


def match(s: str) -> str:
    """Loose form for comparing anchors and text: straight quotes, '-' dashes, joined hyphenation, one space."""
    s = unicodedata.normalize("NFKC", s)
    for a, b in _PUNCT.items():
        s = s.replace(a, b)
    s = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", s)
    return re.sub(r"\s+", " ", s).strip()


# Early-modern spellings (Hobbes 1651 and similar) -> modern, for the search copy only.
EARLY_MODERN = {
    "soveraign": "sovereign", "soveraigne": "sovereign", "soveraignes": "sovereigns", "soveraigns": "sovereigns",
    "soveraignty": "sovereignty", "lawes": "laws", "warre": "war", "warres": "wars", "feare": "fear",
    "feares": "fears", "naturall": "natural", "onely": "only", "generall": "general", "publique": "public",
    "civill": "civil", "kingdome": "kingdom", "darknesse": "darkness", "poore": "poor", "common-wealth": "commonwealth", "severall": "several", "perpetuall": "perpetual", "restlesse": "restless",
    "equall": "equal", "mutuall": "mutual", "hath": "has", "doth": "does", "bee": "be", "wee": "we",
    "selfe": "self", "himselfe": "himself", "owne": "own", "lyberty": "liberty",
    "politique": "politic", "politiques": "politics", "quarrell": "quarrel",
    "vertue": "virtue", "vertues": "virtues", "musique": "music", "ayd": "aid", "sayd": "said",
    "mortall": "mortal", "immortall": "immortal", "authoritie": "authority", "speake": "speak",
    }
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")


def search_copy(s: str) -> str:
    """Spelling-normalized copy used only for the BM25 column; never displayed."""
    s = match(s)
    return _WORD.sub(lambda m: EARLY_MODERN.get(m.group(0).lower(), m.group(0)), s)
