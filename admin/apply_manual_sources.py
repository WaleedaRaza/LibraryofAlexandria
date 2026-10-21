"""Verify editor-found links and add them to the local Launch 72 run."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.services.reading_desk import _expected_pages, _initial_candidate, _probe_candidate, assess_edition

RUN_PATH = settings.BASE_DIR / "data" / "launch_72_sourcing.json"
SOURCES_PATH = settings.BASE_DIR / "library" / "reading_lists" / "manual_sources.json"


async def apply() -> None:
    run = json.loads(RUN_PATH.read_text(encoding="utf-8"))
    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))["books"]
    by_title = {book["title"].casefold(): book for book in run["books"]}
    async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=5)) as client:
        for source in sources:
            book = by_title.get(source["title"].casefold())
            if not book:
                continue
            if any(item["url"] == source["url"] for item in book["results"]):
                continue
            candidate = _initial_candidate(
                {"title": source["label"], "href": source["url"], "body": "Editor found source"},
                book,
                "editor source",
                1,
            )
            if not candidate:
                continue
            checked = await _probe_candidate(candidate, client, book, full_inspection=True)
            if not checked["viewable"]:
                print(f"not a direct PDF: {source['title']} · {checked['state']}")
                continue
            checked["score"] = max(0, min(99, round(checked["score"] * 0.55)))
            checked["source_page"] = source["source_page"]
            checked["rights"] = source["rights"]
            checked["reasons"].append("editor verified source")
            assess_edition(book, checked, await _expected_pages(book, client))
            book["results"].insert(0, checked)
            book["results"].sort(key=lambda item: (item["viewable"], item["score"]), reverse=True)
            for index, item in enumerate(book["results"], 1):
                item["rank"] = index
            print(f"added: {source['title']} · {checked['page_count']} pages")
    run["updated_at"] = datetime.now(timezone.utc).isoformat()
    RUN_PATH.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(apply())
