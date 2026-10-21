"""Promote individually reviewed link editions into the deployable catalog.

This is intentionally explicit: a working PDF link is not a rights review.
Example: python -m admin.approve_link_books --title Dracula --confirm-public-sharing
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from app.config import settings

STAGED_PATH = settings.BASE_DIR / "data" / "link_books_staged.json"
PUBLIC_PATH = settings.BASE_DIR / "library" / "link_catalog.json"


def approve(titles: list[str]) -> list[dict]:
    staged = json.loads(STAGED_PATH.read_text(encoding="utf-8"))["books"]
    requested = {title.casefold().strip() for title in titles}
    selected = [book for book in staged if book["title"].casefold() in requested]
    found = {book["title"].casefold() for book in selected}
    if found != requested:
        raise ValueError(f"Titles not in staged set: {', '.join(sorted(requested - found))}")
    existing = json.loads(PUBLIC_PATH.read_text(encoding="utf-8")) if PUBLIC_PATH.exists() else {"version": 1, "books": []}
    by_id = {book["id"]: book for book in existing["books"]}
    approved_at = datetime.now(timezone.utc).isoformat()
    for book in selected:
        by_id[book["id"]] = {
            **book,
            "rights_status": "approved",
            "visibility": "public",
            "reviewed_at": approved_at,
        }
    payload = {"version": 1, "book_count": len(by_id), "books": list(by_id.values())}
    PUBLIC_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", action="append", required=True, help="Exact staged title; repeat for multiple books")
    parser.add_argument("--confirm-public-sharing", action="store_true", help="Confirm your review before publication")
    args = parser.parse_args()
    if not args.confirm_public_sharing:
        parser.error("No records changed. Pass --confirm-public-sharing only after reviewing each source.")
    selected = approve(args.title)
    print(f"Approved {len(selected)} source links for the public catalog. Review {PUBLIC_PATH} before deployment.")


if __name__ == "__main__":
    main()
