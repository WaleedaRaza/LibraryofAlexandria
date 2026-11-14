"""Share cards for a Name Ten result: 1200x630 for link previews, 1080x1350 for posting as an image.

Drawn with Pillow from the stored play; fonts are bundled OFL files in
static/fonts/card (Pixelify Sans stands in for the site's VT323).
"""

from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = Path(__file__).resolve().parents[3] / "static" / "fonts" / "card"
BG = (7, 7, 10)
RAISED = (16, 16, 20)
INK = (243, 239, 228)
DIM = (163, 158, 145)
FAINT = (92, 88, 79)
GOLD = (227, 179, 65)
GOLD_DEEP = (168, 121, 27)
SIZES = {"wide": (1200, 630), "tall": (1080, 1350)}


@lru_cache(maxsize=32)
def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def pixel(size):
    return _font("PixelifySans-Medium.ttf", size)


def mono(size, bold=False):
    return _font("IBMPlexMono-Bold.ttf" if bold else "IBMPlexMono-Regular.ttf", size)


def sans(size, bold=False):
    return _font("WorkSans-Bold.ttf" if bold else "WorkSans-Regular.ttf", size)


def _fit(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> str:
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int, lines: int) -> list[str]:
    words, out, line = text.split(), [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= width:
            line = trial
            continue
        out.append(line)
        line = word
        if len(out) == lines:
            break
    if len(out) < lines and line:
        out.append(line)
    if len(out) == lines and " ".join(out) != " ".join(words):
        out[-1] = _fit(draw, out[-1] + " …", font, width)
    return [entry for entry in out if entry]


def score_line(play: dict) -> str:
    facts = play.get("findings_json") or {}
    if facts.get("early"):
        return "an early list: scored against the first players"
    return f"rarer together than {play['score']} in 100 lists"


def render(play: dict, size: str = "wide") -> bytes:
    width, height = SIZES.get(size, SIZES["wide"])
    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)
    pad = 56 if size == "wide" else 72
    draw.rectangle([18, 18, width - 19, height - 19], outline=GOLD_DEEP, width=2)

    verdict = play.get("verdict_json") or {}
    epithet = verdict.get("epithet") or "A reader"
    badges = [badge["name"] for badge in (play.get("badges_json") or [])]
    titles = [item["title"] for item in sorted(play["items"], key=lambda item: item["position"])]

    draw.text((pad, pad - 8), "LIBXNDR · NAME TEN", font=mono(22, bold=True), fill=GOLD)

    if size == "wide":
        left = 470
        draw.text((pad - 8, 96), str(play["score"]), font=pixel(220), fill=GOLD)
        y = 352
        for line in _wrap(draw, score_line(play), mono(18), left - pad, 2):
            draw.text((pad, y), line, font=mono(18), fill=DIM)
            y += 26
        y += 22
        size = next((s for s in (56, 48, 40, 34) if draw.textlength(epithet, font=pixel(s)) <= left - pad), None)
        if size:
            draw.text((pad, y), epithet, font=pixel(size), fill=INK)
        else:
            for line in _wrap(draw, epithet, pixel(32), left - pad, 2):
                draw.text((pad, y), line, font=pixel(32), fill=INK)
                y += 36
        x = left + 30
        draw.line([x - 30, 70, x - 30, height - 120], fill=(40, 39, 36), width=1)
        for index, title in enumerate(titles):
            row = 82 + index * 44
            draw.text((x, row + 2), f"{index + 1:02d}", font=mono(20), fill=FAINT)
            draw.text((x + 46, row), _fit(draw, title, sans(27), width - x - 46 - pad), font=sans(27), fill=INK)
        footer = height - 78
    else:
        draw.text((pad - 10, 120), str(play["score"]), font=pixel(300), fill=GOLD)
        y = 460
        for line in _wrap(draw, score_line(play), mono(26), width - 2 * pad, 2):
            draw.text((pad, y), line, font=mono(26), fill=DIM)
            y += 36
        y += 20
        for line in _wrap(draw, epithet, pixel(72), width - 2 * pad, 2):
            draw.text((pad, y), line, font=pixel(72), fill=INK)
            y += 80
        y += 24
        for index, title in enumerate(titles):
            draw.text((pad, y + 4), f"{index + 1:02d}", font=mono(24), fill=FAINT)
            draw.text((pad + 56, y), _fit(draw, title, sans(32), width - 2 * pad - 56), font=sans(32), fill=INK)
            y += 50
        footer = height - 96

    x = pad
    for name in badges:
        label = name.upper()
        box = draw.textlength(label, font=mono(17, bold=True)) + 28
        if x + box > width - pad - 230:
            break
        draw.rectangle([x, footer - 6, x + box, footer + 30], outline=GOLD_DEEP, fill=RAISED)
        draw.text((x + 14, footer), label, font=mono(17, bold=True), fill=GOLD)
        x += box + 12
    site = "libxndr.com/ten"
    draw.text((width - pad - draw.textlength(site, font=mono(22)), footer), site, font=mono(22), fill=DIM)

    buffer = io.BytesIO()
    image.save(buffer, "PNG", optimize=True)
    return buffer.getvalue()
