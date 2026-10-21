"""Read-only production and catalog preflight for a LibXNDR release."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from urllib.parse import quote

import httpx

from app.config import settings
from app.db.database import get_supabase, init_db, is_sqlite_mode


def check(condition: bool, success: str, failure: str, errors: list[str]) -> None:
    print(("PASS " + success) if condition else ("FAIL " + failure))
    if not condition:
        errors.append(failure)


def distributed_sample(books: list[dict], count: int) -> list[dict]:
    """Select books across the full catalog rather than only its first titles."""
    if count <= 0 or count >= len(books):
        return books
    if count == 1:
        return [books[len(books) // 2]]
    return [books[round(index * (len(books) - 1) / (count - 1))] for index in range(count)]


def validate_public_pdf(bucket: str, book: dict) -> str | None:
    """Return an error description when the public object is not a real PDF."""
    asset_key = quote(book["asset_key"], safe="/")
    url = f"https://storage.googleapis.com/{bucket}/{asset_key}"
    try:
        response = httpx.get(
            url,
            headers={"Range": "bytes=0-1023"},
            timeout=20,
            follow_redirects=True,
        )
    except httpx.HTTPError as exc:
        return f"{book['id']}: {type(exc).__name__}"
    if response.status_code not in {200, 206}:
        return f"{book['id']}: HTTP {response.status_code}"
    if b"%PDF-" not in response.content[:1024]:
        return f"{book['id']}: response is not a PDF"
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf-root", type=Path, help="Also check every catalog file in a local folder")
    parser.add_argument("--remote", action="store_true", help="Check Supabase schema, private bucket, and sample PDFs")
    parser.add_argument("--sample", type=int, default=8, help="Number of evenly distributed public PDFs to check")
    parser.add_argument("--all-pdfs", action="store_true", help="Validate every public catalog PDF")
    args = parser.parse_args()
    errors: list[str] = []
    catalog_path = Path(settings.LIBRARY_CATALOG_PATH)
    check(catalog_path.is_file(), f"catalog exists at {catalog_path}", "catalog file is missing", errors)
    if not catalog_path.is_file():
        raise SystemExit(1)
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    books = payload.get("books") or []
    ids = [book.get("id") for book in books]
    assets = [book.get("asset_key") for book in books]
    check(bool(books), f"catalog has {len(books)} books", "catalog is empty", errors)
    check(len(ids) == len(set(ids)) and all(ids), "book IDs are unique", "book IDs are missing or duplicated", errors)
    check(len(assets) == len(set(assets)) and all(assets), "asset keys are unique", "asset keys are missing or duplicated", errors)
    if args.pdf_root:
        missing = [book["source_filename"] for book in books if not (args.pdf_root / book["source_filename"]).is_file()]
        check(not missing, f"all {len(books)} local PDFs exist", f"{len(missing)} local PDFs are missing", errors)
    if settings.is_production:
        for item in settings.production_errors():
            errors.append(item)
            print("FAIL " + item)
    if args.remote:
        check(not is_sqlite_mode(), "Supabase credentials are configured", "Supabase credentials are not configured", errors)
        if not is_sqlite_mode():
            try:
                init_db()
                print("PASS production database schema is current")
            except Exception as exc:
                errors.append("production database schema check failed")
                print(f"FAIL production database schema check failed ({type(exc).__name__})")
            try:
                supabase = get_supabase()
                bucket = supabase.storage.get_bucket(settings.SUPABASE_STORAGE_BUCKET)
                public = bucket.get("public") if isinstance(bucket, dict) else getattr(bucket, "public", None)
                check(public is False, "book bucket is private", "book bucket is missing or public", errors)
                check(bool(settings.GCS_LIBRARY_BUCKET), "public collection bucket is configured", "public collection bucket is not configured", errors)
                selected = books if args.all_pdfs else distributed_sample(books, max(0, args.sample))
                with ThreadPoolExecutor(max_workers=min(16, max(1, len(selected)))) as executor:
                    results = list(
                        executor.map(
                            lambda book: validate_public_pdf(settings.GCS_LIBRARY_BUCKET, book),
                            selected,
                        )
                    )
                invalid = [result for result in results if result]
                if invalid:
                    preview = "; ".join(invalid[:5])
                    raise RuntimeError(f"{len(invalid)} invalid public PDFs ({preview})")
                label = "all" if args.all_pdfs else "distributed"
                print(f"PASS {len(selected)} {label} public PDF checks opened")
            except Exception as exc:
                errors.append("remote storage sample failed")
                print(f"FAIL remote storage sample failed ({type(exc).__name__})")
    print(f"\n{'READY' if not errors else 'NOT READY'} · {len(errors)} failed checks")
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
