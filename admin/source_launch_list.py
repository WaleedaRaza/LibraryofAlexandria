"""Run the local PDF discovery algorithm over a saved reading list.

Usage:
    .venv/bin/python -m admin.source_launch_list --batch 1
    .venv/bin/python -m admin.source_launch_list --all

Results are checkpoints in data/launch_72_sourcing.json so a long run can be
inspected while it is still in progress and resumed without repeating books.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.config import settings
from app.services.reading_desk import MAX_PDF_BYTES, _download_limited, _expected_pages, assess_edition, find_readings, pdf_book_evidence

LIST_PATH = settings.BASE_DIR / "library" / "reading_lists" / "launch_72.json"
OUTPUT_PATH = settings.BASE_DIR / "data" / "launch_72_sourcing.json"


def _key(book: dict) -> str:
    return f"{book['title'].casefold()}|{book['author'].casefold()}"


def _save(payload: dict) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(OUTPUT_PATH)


async def source(books: list[dict], all_books: list[dict], concurrency: int, *, retry_missing: bool = False) -> dict:
    prior = json.loads(OUTPUT_PATH.read_text(encoding="utf-8")) if OUTPUT_PATH.exists() else {"books": []}
    completed = {_key(book): book for book in prior.get("books", []) if book.get("results") is not None}
    semaphore = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    total = len(books)

    async def run(index: int, book: dict) -> None:
        key = _key(book)
        if key in completed and (not retry_missing or any(item.get("viewable") for item in completed[key].get("results", []))):
            print(f"[{index + 1}/{total}] cached: {book['title']}", flush=True)
            return
        async with semaphore:
            print(f"[{index + 1}/{total}] searching: {book['title']}", flush=True)
            try:
                results = await find_readings(book["title"], book["author"])
                record = {**book, "results": results[:8], "error": None}
            except Exception as exc:
                record = {**book, "results": [], "error": str(exc)[:240]}
            async with lock:
                completed[key] = record
                ordered = [completed[_key(item)] for item in all_books if _key(item) in completed]
                payload = {
                    "name": "The Launch 72 — sourcing run",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "total": len(all_books),
                    "completed": len(ordered),
                    "books": ordered,
                }
                _save(payload)
                direct = sum(item.get("viewable", False) for item in results)
                best = next((item for item in results if item.get("viewable") and (item.get("page_count") or 0) >= 40), None)
                print(f"[{len(ordered)}/{total}] {book['title']}: {direct} PDFs; first look: {best['page_count'] if best else 'none'} pages", flush=True)

    await asyncio.gather(*(run(index, book) for index, book in enumerate(books)))
    return json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))


async def reassess(concurrency: int) -> dict:
    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    semaphore = asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(timeout=10) as client:
        async def update(book: dict) -> None:
            async with semaphore:
                expected = await _expected_pages(book, client)
                for item in book.get("results", []):
                    if item.get("rights") == "open repository":
                        item["rights"] = "archive host; rights unverified"
                    assess_edition(book, item, expected, force=True)
                book["results"].sort(key=lambda item: (item.get("viewable", False), item["score"]), reverse=True)
                for index, item in enumerate(book["results"], 1):
                    item["rank"] = index
                print(f"reassessed: {book['title']} · expected {expected or '?'} pages", flush=True)

        await asyncio.gather(*(update(book) for book in payload["books"]))
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save(payload)
    return payload


async def deepen(concurrency: int) -> dict:
    """Check opening-page identity and try to count unmeasured PDF candidates."""
    payload = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    semaphore = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    timeout = httpx.Timeout(18.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout, limits=httpx.Limits(max_connections=concurrency + 2)) as client:
        async def update(book: dict) -> None:
            direct = [item for item in book.get("results", []) if item.get("viewable")]
            has_strong = any(item.get("page_count") and item["page_count"] >= 40 and item["score"] >= 65 and item.get("edition_fit") == "plausible length" for item in direct)
            targets = direct[:1] if has_strong else direct[:4]
            for item in targets:
                if item.get("size_bytes") and item["size_bytes"] > MAX_PDF_BYTES:
                    continue
                async with semaphore:
                    try:
                        data, _, final_url = await _download_limited(client, item["final_url"], MAX_PDF_BYTES)
                        if not data.lstrip().startswith(b"%PDF-"):
                            continue
                        item["final_url"] = final_url
                        item["size_bytes"] = len(data)
                        item.update(await asyncio.to_thread(pdf_book_evidence, data, book))
                    except (httpx.HTTPError, OSError, ValueError) as exc:
                        item["deep_check_error"] = str(exc)[:160]
            expected = await _expected_pages(book, client)
            for item in book.get("results", []):
                assess_edition(book, item, expected, force=True)
            book["results"].sort(key=lambda item: (item.get("viewable", False), item["score"]), reverse=True)
            for index, item in enumerate(book["results"], 1):
                item["rank"] = index
            async with lock:
                payload["updated_at"] = datetime.now(timezone.utc).isoformat()
                _save(payload)
                counted = sum(bool(item.get("page_count")) for item in book.get("results", []) if item.get("viewable"))
                print(f"deep checked: {book['title']} · {counted} counted PDFs", flush=True)

        await asyncio.gather(*(update(book) for book in payload["books"]))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Source the Launch 72 in manageable batches")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--batch", type=int, choices=range(1, 7))
    group.add_argument("--all", action="store_true")
    group.add_argument("--reassess", action="store_true")
    group.add_argument("--deepen", action="store_true")
    group.add_argument("--retry-missing", action="store_true")
    parser.add_argument("--concurrency", type=int, default=3)
    args = parser.parse_args()
    reading_list = json.loads(LIST_PATH.read_text(encoding="utf-8"))
    all_books = reading_list["books"]
    books = all_books
    if args.reassess:
        asyncio.run(reassess(max(1, min(args.concurrency, 5))))
        return
    if args.deepen:
        asyncio.run(deepen(max(1, min(args.concurrency, 5))))
        return
    if args.batch:
        size = reading_list["batch_size"]
        books = books[(args.batch - 1) * size : args.batch * size]
    asyncio.run(source(books, all_books, max(1, min(args.concurrency, 5)), retry_missing=args.retry_missing))


if __name__ == "__main__":
    main()
