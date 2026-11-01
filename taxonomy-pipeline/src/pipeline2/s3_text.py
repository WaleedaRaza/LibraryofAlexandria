"""S3: clean text in reading order with paragraphs and an offset map back to page and box."""
from __future__ import annotations

from .model import Line, Para

_END = tuple('.!?:;"\'”’)]')


def run(lines: list[Line]) -> tuple[str, list[Para], list[tuple[int, int, int, tuple]]]:
    """Returns (text, paragraphs, offset_map[(start, end, page, bbox)])."""
    out: list[str] = []
    pos = 0
    paras: list[Para] = []
    omap: list[tuple[int, int, int, tuple]] = []
    cur = None          # current paragraph dict
    prev_block = None

    def emit(s: str) -> int:
        nonlocal pos
        out.append(s)
        pos += len(s)
        return pos

    def close():
        nonlocal cur
        if cur:
            paras.append(Para(cur["start"], pos, cur["p0"], cur["p1"], cur["heading"], "".join(out)[cur["start"]:pos]))
            cur = None

    for l in lines:
        if l.role not in ("body", "heading"):
            continue
        is_head = l.role == "heading"
        block = (l.page, l.block)
        new_para = cur is None or is_head or cur["heading"] or block != prev_block
        if new_para and cur and not is_head and not cur["heading"] and l.page != cur["p1"]:
            # paragraph running over a page break: keep going if the previous one did not end a sentence
            last = cur["last"]
            if not last.endswith(_END) and l.text[:1].islower():
                new_para = False
        if new_para:
            close()
            if pos:
                emit("\n\n")
            cur = {"start": pos, "p0": l.page, "p1": l.page, "heading": is_head, "last": ""}
            start = pos
            emit(l.text)
        else:
            last = cur["last"]
            if last.endswith("-") and l.text[:1].islower() and not last.endswith("--"):
                out[-1] = out[-1][:-1]      # drop the hyphen we already wrote
                pos -= 1
                start = pos
                emit(l.text)
            else:
                emit(" ")
                start = pos
                emit(l.text)
            cur["p1"] = l.page
        omap.append((start, pos, l.page, (round(l.x0, 1), round(l.y0, 1), round(l.x1, 1), round(l.y1, 1))))
        cur["last"] = l.text
        prev_block = block
    close()
    return "".join(out), paras, omap
