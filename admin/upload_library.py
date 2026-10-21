"""Upload cataloged founding-collection PDFs to Google Cloud Storage.

The command is resumable: successful book IDs are written to a local state
file so a long corpus upload can be restarted safely.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

from google.auth.credentials import Credentials
from google.api_core.exceptions import PreconditionFailed
from google.cloud import storage

from app.config import settings


class GcloudCredentials(Credentials):
    """Refresh short-lived credentials through the already-authenticated gcloud CLI."""

    def refresh(self, request) -> None:  # noqa: ARG002
        self.token = subprocess.check_output(
            ["gcloud", "auth", "print-access-token"],
            text=True,
        ).strip()
        self.expiry = datetime.now() + timedelta(minutes=50)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=Path("library/catalog.json"))
    parser.add_argument("--pdf-root", type=Path, required=True)
    parser.add_argument("--state", type=Path, default=Path("data/uploaded-books.json"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--bucket", default=settings.GCS_LIBRARY_BUCKET)
    parser.add_argument("--project", default="libxndr")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    completed = set()
    if args.state.exists():
        completed = set(json.loads(args.state.read_text(encoding="utf-8")))

    pending = [book for book in catalog["books"] if book["id"] not in completed]
    if args.limit:
        pending = pending[: args.limit]
    print(f"{len(pending)} PDFs pending; {len(completed)} already uploaded")
    if args.dry_run:
        total = sum((args.pdf_root / book["source_filename"]).stat().st_size for book in pending)
        print(f"Dry run: {total / 1024**3:.2f} GiB would be uploaded")
        return
    if not args.bucket:
        raise SystemExit("Set GCS_LIBRARY_BUCKET or pass --bucket")
    if args.workers < 1 or args.workers > 16:
        raise SystemExit("--workers must be between 1 and 16")

    credentials = GcloudCredentials()
    credentials.refresh(None)
    client = storage.Client(project=args.project, credentials=credentials)
    bucket = client.bucket(args.bucket)
    args.state.parent.mkdir(parents=True, exist_ok=True)

    def upload(book: dict) -> str:
        source = args.pdf_root / book["source_filename"]
        blob = bucket.blob(book["asset_key"])
        blob.cache_control = "public, max-age=86400"
        try:
            blob.upload_from_filename(
                source,
                content_type="application/pdf",
                if_generation_match=0,
                timeout=600,
            )
        except PreconditionFailed:
            blob.reload()
            if blob.size != source.stat().st_size:
                raise RuntimeError(f"Existing object has the wrong size: {book['asset_key']}")
        return book["id"]

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(upload, book): book for book in pending}
        for index, future in enumerate(as_completed(futures), 1):
            book = futures[future]
            try:
                completed.add(future.result())
            except Exception as exc:
                print(f"Stopped at {book['title']}: {exc}")
                raise
            args.state.write_text(json.dumps(sorted(completed), indent=2) + "\n", encoding="utf-8")
            print(f"[{index}/{len(pending)}] {book['title']}")

    print(f"Upload complete: {len(completed)} PDFs available")


if __name__ == "__main__":
    main()
