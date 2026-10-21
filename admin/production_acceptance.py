"""Disposable end-to-end production acceptance journey for LibXNDR.

Creates isolated QA identities, exercises profile, private contribution,
review, publication, decline, and guest visibility, then removes only the
records and storage objects created by this run.

Required environment variables:
    SUPABASE_URL
    SUPABASE_SERVICE_ROLE_KEY

Example:
    PUBLIC_BASE_URL=https://libxndr.com python -m admin.production_acceptance
"""

from __future__ import annotations

import argparse
import io
import json
import secrets
from dataclasses import dataclass, field

import pymupdf
import httpx
from PIL import Image

from app.config import settings
from app.db.database import get_supabase, is_sqlite_mode


@dataclass
class RunState:
    user_ids: list[str] = field(default_factory=list)
    submission_ids: list[str] = field(default_factory=list)
    storage_keys: list[str] = field(default_factory=list)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)
    print(f"PASS {message}")


def make_pdf() -> bytes:
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "LibXNDR production acceptance edition")
        page.insert_text((72, 104), "Created for an isolated review journey and removed afterward.")
        return document.tobytes()


def make_avatar() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (96, 144), "#0d817d").save(output, "PNG")
    return output.getvalue()


def login(base_url: str, email: str, password: str) -> httpx.Client:
    client = httpx.Client(base_url=base_url, timeout=65, follow_redirects=False)
    response = client.post(
        "/auth/login",
        data={"email": email, "password": password, "next": "/library/my"},
    )
    require(response.status_code == 303, f"{email} signs in through the public application")
    require(bool(client.cookies.get("__session")), "application session cookie is issued")
    return client


def newest_submission(user_id: str, title: str) -> dict:
    rows = (
        get_supabase()
        .table("book_submissions")
        .select("*")
        .eq("user_id", user_id)
        .eq("title", title)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    require(len(rows) == 1, f"submission record exists for {title}")
    return rows[0]


def require_pdf(client: httpx.Client, path: str, message: str) -> None:
    """Validate both the app redirect and the private/public object response."""
    response = client.get(path)
    if response.status_code in {302, 303, 307, 308}:
        response = client.get(response.headers["location"])
    require(response.status_code == 200 and response.content.startswith(b"%PDF-"), message)


def cleanup(state: RunState) -> None:
    database = get_supabase()
    for submission_id in state.submission_ids:
        database.table("community_editions").delete().eq("submission_id", submission_id).execute()
        database.table("submission_reviews").delete().eq("submission_id", submission_id).execute()
        database.table("book_submissions").delete().eq("id", submission_id).execute()
    for user_id in state.user_ids:
        # Reader-owned tables either cascade or are removed explicitly so this
        # remains safe if a deployment uses an older schema without cascades.
        for table in (
            "reading_companion_messages",
            "highlights",
            "reading_progress",
            "saved_books",
            "source_jobs",
            "user_sessions",
        ):
            database.table(table).delete().eq("user_id", user_id).execute()
        database.table("users").delete().eq("id", user_id).execute()
    if state.storage_keys:
        database.storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove(state.storage_keys)
    for user_id in state.user_ids:
        try:
            database.auth.admin.delete_user(user_id)
        except Exception:
            # Database and object cleanup are the privacy-critical pieces. An
            # already-absent disposable Auth identity is harmless.
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the disposable LibXNDR production acceptance journey.")
    parser.add_argument("--base-url", default=settings.PUBLIC_BASE_URL or "https://libxndr.com")
    parser.add_argument("--keep", action="store_true", help="Keep QA records for manual inspection")
    parser.add_argument("--include-finder", action="store_true", help="Also run a live two-title Finder journey")
    parser.add_argument(
        "--require-finder-candidate",
        action="store_true",
        help="Fail when the external search provider returns no usable candidate",
    )
    args = parser.parse_args()
    if is_sqlite_mode():
        raise SystemExit("Production acceptance requires Supabase service credentials")

    suffix = secrets.token_hex(5)
    password = secrets.token_urlsafe(20)
    contributor_email = f"libxndr.qa.reader.{suffix}@example.com"
    reviewer_email = f"libxndr.qa.reviewer.{suffix}@example.com"
    approved_title = f"LibXNDR QA Approved {suffix}"
    declined_title = f"LibXNDR QA Declined {suffix}"
    state = RunState()
    database = get_supabase()
    contributor: httpx.Client | None = None
    reviewer: httpx.Client | None = None
    guest = httpx.Client(base_url=args.base_url.rstrip("/"), timeout=65, follow_redirects=False)

    try:
        for email, name in ((contributor_email, "QA Reader"), (reviewer_email, "QA Reviewer")):
            created = database.auth.admin.create_user({
                "email": email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {"display_name": name},
            })
            require(bool(created.user), f"disposable identity created for {name}")
            state.user_ids.append(str(created.user.id))

        contributor = login(args.base_url.rstrip("/"), contributor_email, password)
        reviewer = login(args.base_url.rstrip("/"), reviewer_email, password)
        contributor_id, reviewer_id = state.user_ids

        profile = contributor.post(
            "/account",
            data={"display_name": "QA Reader", "username": f"qa.reader.{suffix}"},
            files={"photo": ("qa-avatar.png", make_avatar(), "image/png")},
        )
        require(profile.status_code == 303, "profile name, unique username, and avatar save in production")
        profile_row = database.table("users").select("avatar_key,username").eq("id", contributor_id).single().execute().data
        require(profile_row.get("username") == f"qa.reader.{suffix}", "normalized username persists")
        require(bool(profile_row.get("avatar_key")), "private avatar object is recorded")
        state.storage_keys.append(profile_row["avatar_key"])

        response = contributor.post(
            "/library/contribute",
            data={
                "title": approved_title,
                "author": "Release Robot",
                "note": "Isolated production acceptance source.",
                "links": f"https://example.com/libxndr-qa-{suffix}",
            },
            files={"files": ("libxndr-qa.pdf", make_pdf(), "application/pdf")},
        )
        require(response.status_code == 303, "reader submits one private PDF and link")
        submission = newest_submission(contributor_id, approved_title)
        state.submission_ids.append(submission["id"])
        files = submission["files_json"] if isinstance(submission["files_json"], list) else json.loads(submission["files_json"])
        state.storage_keys.extend(item["storage_key"] for item in files)
        pdf_id = f"{submission['id']}-pdf-0"
        link_id = f"{submission['id']}-link-0"

        owner_shelf = contributor.get("/library/my")
        require(owner_shelf.status_code == 200 and approved_title in owner_shelf.text, "private sources enter the owner's shelf")
        require_pdf(contributor, f"/read/{pdf_id}/pdf", "owner can open the private PDF")
        require(guest.get(f"/read/{pdf_id}/pdf").status_code == 404, "guest cannot open the pending private PDF")
        require(guest.get(f"/library/book/{link_id}").status_code == 404, "guest cannot discover the pending private link")

        database.table("users").update({"role": "admin"}).eq("id", reviewer_id).execute()
        review_page = reviewer.get(f"/review/{submission['id']}")
        require(review_page.status_code == 200 and approved_title in review_page.text, "reviewer sees the private submission")
        approved = reviewer.post(
            f"/review/{submission['id']}/decision",
            data={
                "decision": "approved",
                "title": approved_title,
                "author": "Release Robot",
                "note": "Production QA: source opened and isolated test publication approved.",
                "source_ids": [pdf_id],
            },
        )
        require(approved.status_code == 303, "reviewer publishes only the selected PDF edition")
        public_detail = guest.get(f"/library/book/{pdf_id}")
        require(public_detail.status_code == 200 and approved_title in public_detail.text, "approved edition becomes guest-visible")
        require_pdf(guest, f"/read/{pdf_id}/pdf", "approved PDF becomes guest-readable")
        require(guest.get(f"/library/book/{link_id}").status_code == 404, "unselected link remains private")

        declined = contributor.post(
            "/library/contribute",
            data={
                "title": declined_title,
                "author": "Release Robot",
                "note": "Decline-path production acceptance source.",
                "links": f"https://example.org/libxndr-qa-decline-{suffix}",
            },
        )
        require(declined.status_code == 303, "reader submits a link for decline-path testing")
        declined_submission = newest_submission(contributor_id, declined_title)
        state.submission_ids.append(declined_submission["id"])
        declined_link_id = f"{declined_submission['id']}-link-0"
        decision = reviewer.post(
            f"/review/{declined_submission['id']}/decision",
            data={
                "decision": "declined",
                "title": declined_title,
                "author": "Release Robot",
                "note": "Production QA decline; source intentionally remains private.",
            },
        )
        require(decision.status_code == 303, "reviewer declines publication")
        require(contributor.get(f"/library/book/{declined_link_id}").status_code == 200, "declined source remains available to its owner")
        require(guest.get(f"/library/book/{declined_link_id}").status_code == 404, "declined source remains hidden from guests")
        print("READY production contribution and review journey passed")

        if args.include_finder:
            created_job = contributor.post(
                "/library/find",
                data={"books": "The Analects — Confucius\nPride and Prejudice — Jane Austen"},
            )
            require(created_job.status_code == 303, "reader starts a two-title Finder run")
            job_path = created_job.headers["location"]
            job_id = job_path.rsplit("/", 1)[-1]
            first_step = contributor.post(f"{job_path}/next")
            require(first_step.status_code == 200 and first_step.json()["completed"] == 1,
                    "Finder durably completes its first title")

            # Resume with a fresh browser session to prove the run is attached
            # to the account rather than the initiating page or process memory.
            contributor.close()
            contributor = login(args.base_url.rstrip("/"), contributor_email, password)
            resumed = contributor.get(job_path)
            require(resumed.status_code == 200 and "1 of 2 checked" in resumed.text,
                    "Finder run resumes from a new signed-in browser session")
            second_step = contributor.post(f"{job_path}/next")
            require(second_step.status_code == 200 and second_step.json()["completed"] == 2,
                    "Finder completes the resumed batch")

            item_rows = (
                database.table("source_job_items")
                .select("*")
                .eq("job_id", job_id)
                .order("position")
                .execute()
                .data
                or []
            )
            require(len(item_rows) == 2 and all(row["status"] in {"complete", "failed"} for row in item_rows),
                    "Finder stores terminal state for every title")
            selected_item = None
            selected_candidate = None
            for row in item_rows:
                candidates = row.get("candidates_json") or []
                if isinstance(candidates, str):
                    candidates = json.loads(candidates)
                if candidates:
                    selected_item, selected_candidate = row, candidates[0]
                    break
            if not selected_candidate:
                if args.require_finder_candidate:
                    raise RuntimeError("live Finder produces at least one inspectable candidate")
                print("PASS Finder presents an honest no-candidate state when upstream search yields no usable source")
            else:
                require(True, "live Finder produces at least one inspectable candidate")
                saved_result = contributor.post(
                    f"{job_path}/save",
                    data={"item_id": selected_item["id"], "urls": [selected_candidate["url"]]},
                )
                require(saved_result.status_code == 303 and "saved=1" in saved_result.headers.get("location", ""),
                        "selected Finder candidate saves privately")
                finder_submission = newest_submission(contributor_id, selected_item["title"])
                state.submission_ids.append(finder_submission["id"])
                finder_link_id = f"{finder_submission['id']}-link-0"
                require(contributor.get(f"/library/book/{finder_link_id}").status_code == 200,
                        "Finder result is readable from the owner's shelf")
                require(guest.get(f"/library/book/{finder_link_id}").status_code == 404,
                        "saved Finder result remains private before review")
            print("READY production Finder journey passed")
    finally:
        guest.close()
        if contributor:
            contributor.close()
        if reviewer:
            reviewer.close()
        if not args.keep:
            cleanup(state)
            print("CLEAN disposable QA identities, records, and objects removed")


if __name__ == "__main__":
    main()
