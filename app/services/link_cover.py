"""Deterministic jacket art for link-only records without uploaded files."""

from __future__ import annotations

import textwrap
import hashlib
from xml.sax.saxutils import escape, quoteattr


PALETTES = (
    ("#15241f", "#d6e4d3", "#8fb69d"),
    ("#25201c", "#e9d9bb", "#d5a66f"),
    ("#1e2330", "#dce1eb", "#9bacd0"),
    ("#302023", "#efdde0", "#d19aa3"),
    ("#252717", "#e8e7cd", "#bdc186"),
    ("#211d2b", "#e4ddec", "#b6a3cf"),
)


def render_link_cover(book: dict) -> str:
    tone = book.get("cover_tone")
    if tone is None:
        tone = int.from_bytes(hashlib.sha1(str(book.get("id", "")).encode()).digest()[:2], "big")
    background, ink, accent = PALETTES[int(tone) % len(PALETTES)]
    title = str(book.get("title") or "Untitled")
    author = escape(str(book.get("author") or "Unknown author"))
    lines = textwrap.wrap(title, width=14, break_long_words=False, break_on_hyphens=False)[:6]
    size = 43 if len(lines) <= 3 else 35
    leading = size * 1.16
    start_y = max(195, 315 - (len(lines) - 1) * leading / 2)
    title_lines = "".join(
        f'<tspan x="38" y="{start_y + index * leading:.1f}">{escape(line)}</tspan>'
        for index, line in enumerate(lines)
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="600" viewBox="0 0 400 600" role="img" aria-label={quoteattr(f"Cover for {title}")}>
  <rect width="400" height="600" fill="{background}"/>
  <path d="M26 28H374M26 572H374" fill="none" stroke="{accent}" stroke-width="2"/>
  <path d="M38 98H362" fill="none" stroke="{accent}" stroke-opacity=".5"/>
  <text x="38" y="70" fill="{accent}" font-family="Avenir Next,sans-serif" font-size="13" letter-spacing="3">WALEED'S LIBRARY</text>
  <text fill="{ink}" font-family="Iowan Old Style,Georgia,serif" font-size="{size}" font-weight="600" letter-spacing="-1">{title_lines}</text>
  <text x="38" y="518" fill="{accent}" font-family="Avenir Next,sans-serif" font-size="18">{author}</text>
  <text x="38" y="554" fill="{accent}" font-family="Avenir Next,sans-serif" font-size="11" letter-spacing="2">{"EXTERNAL EDITION  ·  OPEN SOURCE LINK" if book.get("availability") == "external_link" else "LIBRARY EDITION  ·  PDF"}</text>
</svg>'''
