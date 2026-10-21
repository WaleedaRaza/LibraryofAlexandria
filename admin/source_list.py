"""Run the source finder over any saved reading list, in batches, with resumable checkpoints.

    .venv/bin/python -m admin.source_list --list wide_net --batch 1
    .venv/bin/python -m admin.source_list --list wide_net --all --concurrency 3

Results land in data/<list>_sourcing.json. Each book keeps its top results so a long run
can be inspected while it is still going and resumed without repeating finished books.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone

from app.config import settings
from app.services.reading_desk import find_readings


def _key(book: dict) -> str:
    return f"{book['title'].casefold()}|{book['author'].casefold()}"


async def source(list_name: str, books: list[dict], all_books: list[dict], concurrency: int) -> None:
    output = settings.BASE_DIR / "data" / f"{list_name}_sourcing.json"
    prior = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {"books": []}
    completed = {_key(book): book for book in prior.get("books", []) if book.get("results") is not None}
    semaphore = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    total = len(books)

    def save() -> None:
        ordered = [completed[_key(item)] for item in all_books if _key(item) in completed]
        payload = {
            "name": f"{list_name} — sourcing run",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "total": len(all_books),
            "completed": len(ordered),
            "books": ordered,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(output)

    async def run(index: int, book: dict) -> None:
        key = _key(book)
        if key in completed:
            return
        async with semaphore:
            try:
                results = await asyncio.wait_for(find_readings(book["title"], book["author"]), timeout=90)
                record = {**book, "results": results[:8], "error": None}
            except Exception as exc:  # keep the run moving; the book can be retried later
                record = {**book, "results": [], "error": str(exc)[:240]}
            async with lock:
                completed[key] = record
                save()
                viewable = [item for item in record["results"] if item.get("viewable")]
                best = next((item for item in viewable if (item.get("page_count") or 0) >= 40), None)
                print(f"[{index + 1}/{total}] {book['title']}: {len(viewable)} PDFs; best: {best['page_count'] if best else 'none'} pages", flush=True)

    await asyncio.gather(*(run(index, book) for index, book in enumerate(books)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", required=True, help="name of a file in library/reading_lists without .json")
    parser.add_argument("--batch", type=int, help="1-based batch number")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--concurrency", type=int, default=3)
    args = parser.parse_args()
    payload = json.loads((settings.BASE_DIR / "library" / "reading_lists" / f"{args.list}.json").read_text(encoding="utf-8"))
    all_books = payload["books"]
    size = payload.get("batch_size", 40)
    if args.all:
        books = all_books
    elif args.batch:
        books = all_books[(args.batch - 1) * size: args.batch * size]
    else:
        raise SystemExit("Pass --batch N or --all")
    print(f"Sourcing {len(books)} of {len(all_books)} titles from {args.list}", flush=True)
    asyncio.run(source(args.list, books, all_books, args.concurrency))


if __name__ == "__main__":
    main()
