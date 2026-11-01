from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Line:
    page: int            # 1-based PDF page
    block: int
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    size: float
    bold: bool
    page_h: float
    page_w: float
    role: str = "body"   # body | heading | furniture | pagenum | note


@dataclass
class Para:
    start: int
    end: int
    page_start: int
    page_end: int
    heading: bool
    text: str


@dataclass
class Division:
    id: str
    level: int
    label: str
    start: int
    end: int
    zone: str            # primary | apparatus | front | back | contents
    ordinal: int = 0     # position among primary divisions of its level (canonical-ish ref)
    page: int = 0


@dataclass
class Unit:
    id: str
    edition_id: str
    division_id: str
    zone: str
    voice: str           # author | commentary
    voice_name: str
    ref: str             # e.g. "Chapter XIII §3", "PROP. VI", "§20"
    start: int
    end: int
    page_start: int
    page_end: int
    text: str
    words: int = 0


@dataclass
class Edition:
    id: str
    path: str
    sha256: str
    pages: int
    producer: str
    has_outline: bool
    detected_title: str
    catalog_title: str = ""
    catalog_author: str = ""
    identity_ok: bool = True
    identity_note: str = ""
    ocr_pages: int = 0
    image_only_pages: list = field(default_factory=list)
