"""Turn a checked Launch 72 run into a review list and Chrome bookmark import."""

from __future__ import annotations

import html
import json
from pathlib import Path

from app.config import settings
from app.services.reading_desk import _title_overlap

RUN_PATH = settings.BASE_DIR / "data" / "launch_72_sourcing.json"
REPORT_PATH = settings.BASE_DIR / "library" / "reading_lists" / "launch_72_first_looks.md"
BOOKMARKS_PATH = settings.BASE_DIR / "library" / "reading_lists" / "launch_72_first_looks_bookmarks.html"


def first_look(book: dict) -> dict | None:
    for item in book.get("results", []):
        if (
            item.get("viewable")
            and (item.get("page_count") or 0) >= 40
            and item.get("score", 0) >= 65
            and item.get("edition_fit") in {"plausible length", "length unknown"}
            and not item.get("summary_warning")
            and _title_overlap(book, item) >= 0.45
        ):
            return item
    return None


def review_candidate(book: dict) -> dict | None:
    for item in book.get("results", []):
        if not item.get("viewable") or item.get("summary_warning"):
            continue
        if item.get("edition_fit") in {"possible excerpt", "possible collection"}:
            continue
        if item.get("page_count") is not None and item["page_count"] < 40:
            continue
        if item.get("score", 0) < 50 or _title_overlap(book, item) < 0.45:
            continue
        return item
    return None


def build() -> dict[str, int]:
    run = json.loads(RUN_PATH.read_text(encoding="utf-8"))
    strong: list[tuple[dict, dict]] = []
    review: list[tuple[dict, dict]] = []
    missing: list[dict] = []
    for book in run["books"]:
        pick = first_look(book)
        if pick:
            strong.append((book, pick))
        else:
            candidate = review_candidate(book)
            if candidate:
                review.append((book, candidate))
            else:
                missing.append(book)

    lines = [
        "# Launch 72 — first-look tabs",
        "",
        f"Checked {run['completed']} of {run['total']} titles. These links were tested for a PDF response; page counts are extracted from the file where shown.",
        "",
        "This is a personal inspection list. A reachable PDF does not establish permission to publish it in the reader-facing library.",
        "",
        f"## Open first ({len(strong)})",
        "",
    ]
    for index, (book, item) in enumerate(strong, 1):
        fit = item.get("edition_fit") or "length unknown"
        source_page = f" · [Source page](<{item['source_page']}>)" if item.get("source_page") else ""
        lines.extend([
            f"{index}. **{book['title']} — {book['author']}** · {item['page_count']} pages · {item['domain']} · {fit}",
            f"   [Open PDF](<{item['final_url']}>) · [Original search link](<{item['url']}>)" + source_page,
            "",
        ])
    lines.extend([f"## Inspect manually ({len(review)})", "", "The link returned a PDF, but the edition or page count needs a browser check.", ""])
    for book, item in review:
        pages = f"{item['page_count']} pages" if item.get("page_count") else "pages unknown"
        lines.extend([
            f"- **{book['title']} — {book['author']}** · {pages} · {item['domain']} · {item.get('edition_fit') or 'unverified length'}",
            f"  [Inspect PDF](<{item['final_url']}>) · [Original search link](<{item['url']}>)",
        ])
    lines.extend(["", f"## Needs a better candidate ({len(missing)})", "", "Search found PDF responses for these titles, but none passed the first-book checks.", ""])
    for book in missing:
        lines.append(f"- {book['title']} — {book['author']}")
    lines.append("")
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")

    entries = "\n".join(
        f'<DT><A HREF="{html.escape(item["final_url"], quote=True)}">{html.escape(book["title"] + " — " + book["author"])}</A>'
        for book, item in strong
    )
    BOOKMARKS_PATH.write_text(
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>\n"
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">\n'
        "<TITLE>Waleed's Launch 72 First Looks</TITLE>\n"
        "<H1>Waleed's Launch 72 First Looks</H1>\n<DL><p>\n"
        f"{entries}\n</DL><p>\n",
        encoding="utf-8",
    )
    return {"first_looks": len(strong), "review": len(review), "missing": len(missing)}


if __name__ == "__main__":
    print(build())
