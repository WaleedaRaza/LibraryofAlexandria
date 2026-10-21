"""Build the deployable library catalog from a directory of PDFs.

Usage:
    python -m admin.build_library_catalog --pdf-root /path/to/batch1books
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path


FEATURED_TITLES = {
    "1984",
    "meditations",
    "the brothers karamazov",
    "being and time",
    "the wealth of nations",
    "the master and margarita",
    "the trial",
    "the myth of sisyphus",
    "the republic",
    "beyond good and evil",
    "the art of war",
    "the human condition",
}


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalize(value)).strip("-")[:72] or "book"


def parse_filename(path: Path) -> tuple[str, str]:
    stem = re.sub(r"\s+", " ", path.stem).strip()
    if " - " in stem:
        title, author = stem.rsplit(" - ", 1)
    else:
        title, author = stem, "Unknown"
    return title.strip(), author.strip()


def load_reference_catalog(pdf_root: Path) -> list[dict]:
    candidates = [
        pdf_root / "library_catalog.json",
        Path("/Volumes/Extreme SSD/cleanbooks/batch1books/library_catalog.json"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    return []


def match_domain(title: str, author: str, reference: list[dict]) -> str:
    haystack = normalize(f"{title} {author}")
    matches = []
    for item in reference:
        reference_title = normalize(item.get("title", ""))
        reference_author = normalize(item.get("author", ""))
        if reference_title and reference_title in haystack:
            score = len(reference_title) + (len(reference_author) if reference_author in haystack else 0)
            matches.append((score, item.get("category") or "General"))
    return max(matches, default=(0, "General"))[1]


def build(pdf_root: Path) -> dict:
    reference = load_reference_catalog(pdf_root)
    books = []
    for path in sorted(pdf_root.rglob("*.pdf")):
        if path.name.startswith("._"):
            continue
        title, author = parse_filename(path)
        fingerprint = hashlib.sha256(str(path.relative_to(pdf_root)).encode()).hexdigest()[:8]
        book_id = f"{slug(f'{title}-{author}')}-{fingerprint}"
        domain = match_domain(title, author, reference)
        books.append(
            {
                "id": book_id,
                "title": title,
                "author": author,
                "domain": domain,
                "source_filename": str(path.relative_to(pdf_root)),
                "asset_key": f"books/{book_id}.pdf",
                "file_size": path.stat().st_size,
                "availability": "pdf_ready",
                "text_status": "pending",
                "rights_status": "curated_free_source",
                "featured": normalize(title) in FEATURED_TITLES,
                "cover_seed": fingerprint,
                "cover_tone": int(fingerprint[:2], 16) % 6,
            }
        )
    return {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(pdf_root),
        "book_count": len(books),
        "books": books,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("library/catalog.json"))
    args = parser.parse_args()
    catalog = build(args.pdf_root.expanduser().resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {catalog['book_count']} books to {args.output}")


if __name__ == "__main__":
    main()
