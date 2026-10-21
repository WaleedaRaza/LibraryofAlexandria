"""Turn a finder sourcing run into review-room submissions, credited to one account.

    SUPABASE_URL=… SUPABASE_SERVICE_ROLE_KEY=… \\
      .venv/bin/python -m admin.import_sourced_submissions --list wide_net --email you@example.com --dry-run
      .venv/bin/python -m admin.import_sourced_submissions --list wide_net --email you@example.com --category Fantasy --limit 40

Each book with verified PDFs becomes one pending submission holding its best links (up to
three), with page counts and hosts in the note. Imported titles are remembered in
data/<list>_imported.json so batches never double-submit. Nothing here publishes anything;
every submission still waits for the reviewer.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re

from app.config import settings
from app.db.database import get_db, get_supabase, is_sqlite_mode
from app.services.reading_desk import _is_gated, _is_open_repository
from app.services.submission_service import SubmissionService

MAX_LINKS = 3


def _user_id(email: str) -> str:
    if is_sqlite_mode():
        row = get_db().execute("SELECT id, role FROM users WHERE lower(email)=?", (email.casefold(),)).fetchone()
        rows = [dict(row)] if row else []
    else:
        rows = get_supabase().table("users").select("id,email,role").ilike("email", email).execute().data or []
        rows = [row for row in rows if row["email"].casefold() == email.casefold()]
    if not rows:
        raise SystemExit(f"No account for {email}")
    if rows[0].get("role") != "admin":
        raise SystemExit(f"{email} is not the reviewer; refusing to credit a bulk import to a non-admin account")
    return rows[0]["id"]


def _best_links(results: list[dict]) -> list[dict]:
    viewable = [item for item in results if item.get("viewable")]

    def rank(item: dict) -> tuple:
        pages = item.get("page_count") or 0
        plausible = 40 <= pages <= 1600
        return (plausible, item.get("score") or 0, pages, item.get("size_bytes") or 0)

    chosen: list[dict] = []
    seen_hosts: set[str] = set()
    for item in sorted(viewable, key=rank, reverse=True):
        url = item.get("final_url") or item.get("url")
        if not url or not url.startswith(("https://", "http://")):
            continue
        # Prefer the canonical archive.org address over a mirror hostname that may rotate.
        match = re.match(r"https?://[^/]*archive\.org/\d+/items/([^/]+)/(.+)$", url)
        if match:
            url = f"https://archive.org/download/{match.group(1)}/{match.group(2)}"
        host = re.sub(r"^[^/]*//([^/]+).*$", r"\1", url)
        if any(url == c["url"] for c in chosen) or _is_gated(host):
            continue
        pages = item.get("page_count") or 0
        # Only files that look like the whole book: a real page count, or an archive file of book size.
        if not (40 <= pages <= 1600 or (not pages and _is_open_repository(host) and (item.get("size_bytes") or 0) >= 1_000_000)):
            continue
        chosen.append({**item, "url": url, "host": host})
        seen_hosts.add(host)
        if len(chosen) == MAX_LINKS:
            break
    return chosen


def _note(book: dict, links: list[dict]) -> str:
    parts = []
    for index, item in enumerate(links, 1):
        pages = f"{item['page_count']} pages" if item.get("page_count") else (f"{item['size_bytes'] / 1048576:.1f} MB" if item.get("size_bytes") else "length unverified")
        parts.append(f"{index}. {item['host']} · {pages}")
    note = f"Found by the LibXNDR finder ({book['category']}). " + " ".join(parts)
    return note[:800]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", required=True)
    parser.add_argument("--email", required=True, help="reviewer account the submissions are credited to")
    parser.add_argument("--category", help="only this category from the list")
    parser.add_argument("--limit", type=int, default=0, help="stop after this many new submissions")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    run_path = settings.BASE_DIR / "data" / f"{args.list}_sourcing.json"
    done_path = settings.BASE_DIR / "data" / f"{args.list}_imported.json"
    books = json.loads(run_path.read_text(encoding="utf-8"))["books"]
    imported: dict[str, str] = json.loads(done_path.read_text(encoding="utf-8")) if done_path.exists() else {}
    user_id = None if args.dry_run else _user_id(args.email)
    service = SubmissionService()
    created = skipped = 0
    for book in books:
        key = f"{book['title'].casefold()}|{book['author'].casefold()}"
        if key in imported or (args.category and book["category"] != args.category):
            continue
        links = _best_links(book.get("results") or [])
        if not links:
            skipped += 1
            continue
        if args.limit and created >= args.limit:
            break
        note = _note(book, links)
        print(f"{'would add' if args.dry_run else 'adding'}: {book['title']} — {book['author']} · {len(links)} links · {note[:90]}…", flush=True)
        if not args.dry_run:
            record = await service.create(user_id=user_id, title=book["title"], author=book["author"], note=note,
                                          links="\n".join(item["url"] for item in links), files=[])
            imported[key] = record["id"]
            done_path.write_text(json.dumps(imported, ensure_ascii=False, indent=2), encoding="utf-8")
        created += 1
    print(f"{created} submissions {'would be' if args.dry_run else ''} created · {skipped} titles had no verified PDF · {len(imported)} imported so far")


if __name__ == "__main__":
    asyncio.run(main())
