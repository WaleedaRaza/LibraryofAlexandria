"""Stage verified Launch 72 links for local library preview.

The output lives under ignored data/ and is never a publication decision.
Run ``python -m admin.stage_launch_links`` after a sourcing pass.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from admin.build_launch_report import first_look

RUN_PATH = settings.BASE_DIR / "data" / "launch_72_sourcing.json"
STAGED_PATH = settings.BASE_DIR / "data" / "link_books_staged.json"


def slug(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_value.casefold()).strip("-")[:70]


def domain_for(category: str) -> str:
    if category.startswith("Fiction"):
        return "Fiction"
    if category == "Poetry":
        return "Poetry"
    if category.startswith("Philosophy"):
        return "Philosophy & History"
    if category.startswith("Science"):
        return "Science & Society"
    return "Life & Creativity"


def stage(run_path: Path = RUN_PATH, output_path: Path = STAGED_PATH) -> dict:
    run = json.loads(run_path.read_text(encoding="utf-8"))
    books = []
    for source_book in run["books"]:
        candidate = first_look(source_book)
        if not candidate:
            continue
        title = source_book["title"]
        author = source_book["author"]
        fingerprint = hashlib.sha256(f"{title}\0{author}".encode()).hexdigest()[:8]
        books.append(
            {
                "id": f"link-{slug(title)}-{fingerprint}",
                "title": title,
                "author": author,
                "domain": domain_for(source_book.get("category", "")),
                "category": source_book.get("category", ""),
                "availability": "external_link",
                "text_status": "external_unindexed",
                "rights_status": "pending_review",
                "visibility": "draft",
                "source_url": candidate["final_url"],
                "original_url": candidate["url"],
                "source_page": candidate.get("source_page"),
                "source_domain": candidate.get("domain"),
                "page_count": candidate.get("page_count"),
                "edition_fit": candidate.get("edition_fit"),
                "cover_seed": fingerprint,
                "cover_tone": int(fingerprint[:2], 16) % 6,
                "featured": False,
            }
        )
    staged = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(run_path),
        "book_count": len(books),
        "books": books,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(staged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return staged


if __name__ == "__main__":
    staged = stage()
    print(f"Staged {staged['book_count']} link-only books at {STAGED_PATH}")
