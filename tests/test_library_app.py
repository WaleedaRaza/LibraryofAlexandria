"""End-to-end checks for the first reader-facing library slice."""

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.catalog_service import CatalogService
from app.services.user_service import UserService


def _pdf_bytes():
    import fitz
    with fitz.open() as document:
        document.new_page().insert_text((72, 72), "A reader's private source.")
        return document.tobytes()


def _submission(client):
    from app.db.database import get_db
    response = client.post("/library/contribute", data={"title": "Private edition", "author": "A Writer",
        "links": "https://example.org/edition", "note": "An edition for review"},
        files=[("files", ("edition.pdf", _pdf_bytes(), "application/pdf"))], follow_redirects=False)
    assert response.status_code == 303
    return dict(get_db().execute("SELECT * FROM book_submissions ORDER BY created_at DESC LIMIT 1").fetchone())


def _switch_reader(client, email):
    client.cookies.clear()
    response = client.post("/auth/register", data={"email": email, "password": "a-good-password", "display_name": email.split("@")[0]}, follow_redirects=False)
    assert response.status_code == 303


def test_production_preview_hosts_return_to_canonical_origin(client, monkeypatch):
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://libxndr.com")

    for deployment_host in ("generated-preview.a.run.app", "service.us-east1.run.app"):
        preview = client.get(
            "/library/book/a-title?preview_links=1",
            headers={"host": deployment_host},
            follow_redirects=False,
        )
        assert preview.status_code == 308
        assert preview.headers["location"] == "https://libxndr.com/library/book/a-title?preview_links=1"

    canonical = client.get(
        "/privacy",
        headers={"host": "internal-service.a.run.app", "x-forwarded-host": "libxndr.com"},
        follow_redirects=False,
    )
    assert canonical.status_code == 200

    health = client.get("/health", headers={"host": "internal-service.a.run.app"}, follow_redirects=False)
    assert health.status_code == 200


def test_session_is_opaque_revocable_expiring_and_role_is_fresh(client):
    from app.db.database import get_db
    from app.services.session_service import SessionService
    _register(client)
    token = client.cookies.get("__session")
    row = get_db().execute("SELECT * FROM user_sessions").fetchone()
    assert token not in row["token_hash"] and len(row["token_hash"]) == 64
    assert client.get("/review").status_code == 403
    get_db().execute("UPDATE users SET role='admin'")
    get_db().commit()
    assert client.get("/review").status_code == 200
    client.post("/auth/logout")
    assert SessionService().user(token) is None
    client.cookies.set("__session", token)
    assert client.get("/account", follow_redirects=False).status_code == 303
    expired = SessionService().create(row["user_id"])
    get_db().execute("UPDATE user_sessions SET expires_at=1")
    get_db().commit()
    assert SessionService().user(expired) is None


def test_profile_username_photo_and_identity_survive_sign_in(client, tmp_path):
    import io
    from PIL import Image
    from app.db.database import get_db
    _register(client)
    photo = io.BytesIO()
    Image.new("RGB", (100, 200), "teal").save(photo, "PNG")
    updated = client.post("/account", data={"display_name": "The Reader", "username": "Book.Reader"},
        files={"photo": ("portrait.png", photo.getvalue(), "image/png")}, follow_redirects=False)
    assert updated.status_code == 303
    row = get_db().execute("SELECT * FROM users").fetchone()
    assert row["username"] == "book.reader"
    with Image.open(tmp_path / row["avatar_key"]) as normalized:
        assert normalized.size == (512, 512) and normalized.format == "JPEG"
    assert client.get("/account/avatar").headers["content-type"] == "image/jpeg"
    invalid = client.post("/account", data={"display_name": "Changed", "username": "bad name!"})
    assert invalid.status_code == 400
    invalid = client.post("/account", data={"display_name": "Changed", "username": "reader"}, files={"photo": ("fake.jpg", b"not an image", "image/jpeg")})
    assert invalid.status_code == 400
    client.post("/auth/logout")
    client.post("/auth/login", data={"email": "reader@example.com", "password": "a-good-password"})
    assert "The Reader" in client.get("/account").text
    _switch_reader(client, "other@example.com")
    collision = client.post("/account", data={"display_name": "Other", "username": "BOOK.READER"})
    assert collision.status_code == 400
    assert client.get("/account/avatar").status_code == 404


def test_private_sources_publish_individually_without_leaking_memory(client):
    from app.db.database import get_db
    _register(client)
    owner_token = client.cookies.get("__session")
    submission = _submission(client)
    pdf_id, link_id = submission["id"] + "-pdf-0", submission["id"] + "-link-0"
    assert "Waiting for Waleed" in client.get("/library/my").text
    assert client.get(f"/read/{pdf_id}/pdf").content.startswith(b"%PDF-")
    highlighted = client.post(f"/read/{pdf_id}/highlights", json={"page_number": 1, "selected_text": "Owner-only secret passage"})
    highlight_id = highlighted.json()["highlight"]["id"]
    client.post(f"/read/{pdf_id}/highlights/{highlight_id}/note", json={"text": "My secret note"})
    client.cookies.clear()
    # Signed out, nothing private is reachable: the reader asks for sign-in before it will even say
    # whether a book exists, and the record and cover routes answer as if the book were not there.
    assert client.get(f"/read/{pdf_id}/pdf").status_code == 401
    for path in (f"/read/{pdf_id}", f"/library/book/{link_id}", f"/library/book/{pdf_id}/cover"):
        assert client.get(path).status_code == 404
    _switch_reader(client, "reviewer@example.com")
    assert client.get(f"/read/{pdf_id}/pdf").status_code == 404
    assert client.get(f"/review/{submission['id']}").status_code == 403
    get_db().execute("UPDATE users SET role='admin' WHERE email='reviewer@example.com'")
    get_db().commit()
    review = client.get(f"/review/{submission['id']}")
    assert review.status_code == 200
    assert "Owner-only secret passage" not in review.text
    assert "My secret note" not in client.get(f"/read/{pdf_id}").text
    assert client.post(f"/read/{pdf_id}/highlights/{highlight_id}/note", json={"text": "tampered"}).status_code == 404
    decision = {"decision": "approved", "title": "Corrected title", "author": "Corrected author",
                "note": "Checked the source and permission.", "source_ids": [pdf_id]}
    assert client.post(f"/review/{submission['id']}/decision", data={**decision, "source_ids": ["not-this-source"]}).status_code == 400
    assert client.post(f"/review/{submission['id']}/decision", data=decision, follow_redirects=False).status_code == 303
    assert client.post(f"/review/{submission['id']}/decision", data=decision).status_code == 400
    assert get_db().execute("SELECT count(*) FROM submission_reviews").fetchone()[0] == 1
    client.cookies.clear()
    # Published: visitors see the record; opening the PDF is for members, and nobody sees the owner's notes.
    assert "Corrected title" in client.get(f"/library/book/{pdf_id}").text
    assert client.get(f"/read/{pdf_id}/pdf").status_code == 401
    _switch_reader(client, "public@example.com")
    assert client.get(f"/read/{pdf_id}/pdf").status_code == 200
    assert "Owner-only secret passage" not in client.get(f"/read/{pdf_id}").text
    assert client.get(f"/library/book/{link_id}").status_code == 404
    client.cookies.set("__session", owner_token)
    assert "My secret note" in client.get("/library/my/memory").text
    assert client.get(f"/library/book/{link_id}").status_code == 200


def test_decline_preserves_private_copy_and_shelf(client):
    from app.db.database import get_db
    _register(client)
    owner_token = client.cookies.get("__session")
    submission = _submission(client)
    _switch_reader(client, "reviewer@example.com")
    get_db().execute("UPDATE users SET role='admin' WHERE email='reviewer@example.com'")
    get_db().commit()
    response = client.post(f"/review/{submission['id']}/decision", data={"decision": "declined", "title": "Private edition",
        "author": "A Writer", "note": "Sharing basis not established."}, follow_redirects=False)
    assert response.status_code == 303
    assert get_db().execute("SELECT count(*) FROM community_editions").fetchone()[0] == 0
    client.cookies.clear()
    client.cookies.set("__session", owner_token)
    assert client.get(f"/read/{submission['id']}-pdf-0/pdf").status_code == 200
    assert "Private edition" in client.get("/library/my").text


def test_cross_site_posts_rejected_and_proxy_origin_allowed(client, monkeypatch):
    _register(client)
    assert client.post("/account", data={"display_name": "Changed"}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/auth/logout", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://libxndr.com")
    response = client.post("/library/contribute", data={"title": "Origin test", "links": "https://example.org/book"},
                           headers={"Origin": "https://libxndr.com"}, follow_redirects=False)
    assert response.status_code == 303
    direct = client.post(
        "/auth/register",
        data={"email": "preview@example.com", "password": "a-good-password", "display_name": "Preview"},
        headers={"Host": "preview.a.run.app", "Origin": "http://preview.a.run.app", "Sec-Fetch-Site": "same-origin"},
        follow_redirects=False,
    )
    assert direct.status_code == 303
    protected = client.get("/library/my")
    assert protected.headers["cache-control"] == "private, no-store"
    assert protected.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    assert "object-src 'none'" in protected.headers["content-security-policy"]


def test_google_pkce_start_callback_and_expired_state(client, monkeypatch):
    from types import SimpleNamespace
    import supabase
    from app.routes import auth
    from app.db.database import get_db
    _register(client)
    user_id = get_db().execute("SELECT id FROM users").fetchone()[0]
    client.cookies.clear()
    monkeypatch.setattr(settings, "GOOGLE_AUTH_ENABLED", True)
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://libxndr.com")
    monkeypatch.setattr(auth, "is_sqlite_mode", lambda: False)
    monkeypatch.setattr(auth, "_public_user", lambda user: {"id": user_id})
    exchanges = []
    def fake_client(url, key, options):
        def sign_in(payload):
            assert payload["options"]["redirect_to"] == "https://libxndr.com/auth/google/callback"
            options.storage.set_item("test-code-verifier", "the-pkce-verifier")
            return SimpleNamespace(url="https://accounts.google.com/mock")
        def exchange(payload):
            exchanges.append(payload)
            return SimpleNamespace(session=object(), user=object())
        return SimpleNamespace(auth=SimpleNamespace(sign_in_with_oauth=sign_in, exchange_code_for_session=exchange))
    monkeypatch.setattr(supabase, "create_client", fake_client)
    started = client.get("/auth/google?next=/account", follow_redirects=False)
    assert started.status_code == 302
    assert client.cookies.get("__session").startswith("oauth.")
    finished = client.get("/auth/google/callback?code=provider-code", follow_redirects=False)
    assert finished.status_code == 303 and finished.headers["location"] == "/account"
    assert exchanges == [{"auth_code": "provider-code", "code_verifier": "the-pkce-verifier"}]
    assert client.get("/account").status_code == 200
    client.cookies.clear()
    failed = client.get("/auth/google/callback?code=provider-code")
    assert failed.status_code == 400 and "Please try again" in failed.text
    assert len(exchanges) == 1


def test_verified_identity_maps_to_stable_legacy_profile(monkeypatch):
    from types import SimpleNamespace
    from app.routes import auth

    legacy = {"id": "stable-reader", "email": "reader@example.com", "display_name": "Reader",
              "username": "reader", "avatar_key": None, "role": "admin"}

    class Query:
        def __init__(self):
            self.operation = None
            self.field = None

        def select(self, *args):
            self.operation = "select"
            return self

        def insert(self, *args):
            self.operation = "insert"
            return self

        def eq(self, field, value):
            self.field = field
            return self

        def limit(self, *args):
            return self

        def execute(self):
            if self.operation == "insert":
                raise RuntimeError("email already belongs to a stable profile")
            return SimpleNamespace(data=[] if self.field == "id" else [legacy])

    monkeypatch.setattr(auth, "get_supabase", lambda: SimpleNamespace(table=lambda name: Query()))
    auth_user = SimpleNamespace(id="provider-identity", email="reader@example.com",
                                user_metadata={"full_name": "Reader From Google"})
    assert auth._public_user(auth_user) == legacy


def test_server_confirmation_and_password_recovery_are_complete(client, monkeypatch):
    from types import SimpleNamespace
    from app.routes import auth

    auth_user = SimpleNamespace(
        id="auth-reader",
        email="reader@example.com",
        user_metadata={"display_name": "Reader"},
    )
    reset_requests = []
    password_updates = []

    class FakeAuth:
        def verify_otp(self, payload):
            assert payload in (
                {"token_hash": "confirmation-hash", "type": "email"},
                {"token_hash": "recovery-hash", "type": "recovery"},
            )
            return SimpleNamespace(user=auth_user, session=object())

        def get_user(self, token):
            assert token == "recovery-access-token"
            return SimpleNamespace(user=auth_user)

        def reset_password_for_email(self, email, options):
            reset_requests.append((email, options))

    fake_auth = FakeAuth()
    fake_admin = SimpleNamespace(update_user_by_id=lambda user_id, attrs: password_updates.append((user_id, attrs)))
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://libxndr.com")
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(auth, "is_sqlite_mode", lambda: False)
    monkeypatch.setattr(auth, "get_supabase_auth_client", lambda: SimpleNamespace(auth=fake_auth))
    monkeypatch.setattr(auth, "get_supabase", lambda: SimpleNamespace(auth=SimpleNamespace(admin=fake_admin)))
    monkeypatch.setattr(auth, "_public_user", lambda user: {"id": str(user.id)})
    monkeypatch.setattr(auth, "_start_session", lambda response, user_id: response.set_cookie("__session", f"session-for-{user_id}"))

    confirmation = client.get("/auth/confirm?token_hash=confirmation-hash&type=email&next=/account", follow_redirects=False)
    assert confirmation.status_code == 303
    assert confirmation.headers["location"] == "/account"

    requested = client.post("/auth/forgot-password", data={"email": "Reader@Example.com"})
    assert requested.status_code == 200
    assert "If an account exists" in requested.text
    assert reset_requests == [("reader@example.com", {"redirect_to": "https://libxndr.com/auth/reset-password"})]

    established = client.post("/auth/recovery-session", json={"access_token": "recovery-access-token"})
    assert established.status_code == 200
    recovery_cookie = client.cookies.get(auth.RECOVERY_COOKIE_NAME)
    assert recovery_cookie.startswith("recovery.")
    # TestClient runs over HTTP; reinsert the production Secure cookie for the
    # remainder of this server-side lifecycle check.
    client.cookies.delete(auth.RECOVERY_COOKIE_NAME)
    client.cookies.set(auth.RECOVERY_COOKIE_NAME, recovery_cookie)
    reset_page = client.get("/auth/reset-password")
    assert 'data-ready="true"' in reset_page.text

    changed = client.post("/auth/reset-password", data={
        "password": "a-new-good-password",
        "confirm_password": "a-new-good-password",
    }, follow_redirects=False)
    assert changed.status_code == 303
    assert changed.headers["location"] == "/library/my?password=changed"
    assert password_updates == [("auth-reader", {"password": "a-new-good-password"})]


def test_recovery_state_is_short_lived_and_tamper_evident(client):
    from app.routes.auth import _read_recovery_cookie, _recovery_cookie

    token = _recovery_cookie("reader-id")
    assert _read_recovery_cookie(token)["user_id"] == "reader-id"
    assert _read_recovery_cookie(token + "tampered") is None
    assert "Forgot password?" in client.get("/auth/login").text
    assert "Account recovery" in client.get("/auth/forgot-password").text


def test_unsafe_redirects_and_confirmation_token_rejected(client):
    from app.routes.auth import _safe_next, _oauth_cookie, _read_oauth_cookie
    for target in ("//evil.example", "/%2Fevil.example", "/\\evil.example", "https://evil.example", "/%0aevil"):
        assert _safe_next(target) == "/library/my"
    assert _safe_next("/read/example") == "/read/example"
    state = _oauth_cookie("verifier", "/account")
    assert _read_oauth_cookie(state)["next"] == "/account"
    assert _read_oauth_cookie(state + "tampered") is None
    assert client.post("/auth/set-session", json={"access_token": "forged-token"}).status_code == 400
    confirmation = client.get("/auth/confirm").text
    assert ".innerHTML" not in confirmation
    confirmation_script = client.get("/static/js/confirm_email.js").text
    assert ".innerHTML" not in confirmation_script
    assert "history.replaceState" in confirmation_script


def test_highlight_input_errors_are_recoverable(client):
    _register(client)
    book_id = CatalogService().get_books(limit=1)[0]["id"]
    for payload in ({"page_number": "oops"}, {"page_number": -1}, {"text_start": 10, "text_end": 2}):
        response = client.post(f"/read/{book_id}/highlights", json={"selected_text": "Selected text", **payload})
        assert response.status_code == 400


def test_reader_rejects_oversized_notes_and_passage_questions(client):
    _register(client)
    book_id = CatalogService().get_books(limit=1)[0]["id"]
    created = client.post(
        f"/read/{book_id}/highlights",
        json={"page_number": 1, "selected_text": "A bounded passage."},
    )
    highlight_id = created.json()["highlight"]["id"]

    note = client.post(
        f"/read/{book_id}/highlights/{highlight_id}/note",
        json={"text": "n" * 20_001},
    )
    question = client.post(
        f"/read/{book_id}/highlights/{highlight_id}/chat",
        json={"question": "q" * 2_001},
    )

    assert note.status_code == 400
    assert question.status_code == 400
    assert "20,000" in note.json()["detail"]
    assert "2,000" in question.json()["detail"]


def test_missing_remote_cover_degrades_to_generated_artwork(client, monkeypatch, tmp_path):
    """A missing optional cover must not make a public book return HTTP 500."""
    from app.services.asset_service import AssetService

    book = CatalogService().get_books(limit=1)[0]
    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)

    def missing_cover(_service, _book):
        raise RuntimeError("Object not found")

    monkeypatch.setattr(AssetService, "signed_cover_url", missing_cover)
    response = client.get(f"/library/book/{book['id']}/cover")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert book["title"] in response.text


def test_durable_batch_finder_is_private_resumable_and_saves_selected_links(client, monkeypatch):
    from app.db import database
    from app.services import finder_job_service
    _register(client)
    owner_token = client.cookies.get("__session")
    created = client.post("/library/find", data={"books": "The Analects — Confucius\nBeloved — Toni Morrison"}, follow_redirects=False)
    assert created.status_code == 303
    job_url = created.headers["location"]
    job_id = job_url.rsplit("/", 1)[-1]
    assert "0 of 2 checked" in client.get(job_url).text
    finder_home = client.get("/library/find")
    assert "Past runs (1)" in finder_home.text
    runs = client.get("/library/find/runs")
    assert "Your source runs" in runs.text
    assert "2 titles" in runs.text

    # Another reader cannot discover, work, cancel, or save this job.
    _switch_reader(client, "finder-other@example.com")
    assert client.get(job_url).status_code == 404
    assert client.post(f"{job_url}/next").status_code == 404
    assert client.post(f"{job_url}/cancel").status_code == 404
    client.cookies.clear()
    client.cookies.set("__session", owner_token)

    async def fake_find(title, author):
        return [{"title": f"{title} full text", "url": f"https://books.example/{title.lower().replace(' ', '-')}",
                 "final_url": f"https://cdn.example/{title.lower().replace(' ', '-')}.pdf", "domain": "cdn.example",
                 "page_count": 240, "score": 91, "viewable": True, "edition_fit": "likely book", "reasons": ["PDF response"]}]
    monkeypatch.setattr(finder_job_service, "find_readings", fake_find)
    first = client.post(f"{job_url}/next")
    assert first.status_code == 200 and first.json()["completed"] == 1

    # Close and reopen the SQLite connection to prove state is not an in-memory task.
    database._sqlite_connection.close()
    database._sqlite_connection = None
    persisted = client.get(job_url)
    assert "1 of 2 checked" in persisted.text and "The Analects full text" in persisted.text
    second = client.post(f"{job_url}/next")
    assert second.json()["status"] == "complete" and second.json()["completed"] == 2
    page = client.get(job_url)
    assert "2 of 2 checked" in page.text and "Contribute selected for review" in page.text
    assert "Anonymously" in page.text and "With my LibXNDR name" in page.text

    from app.services.finder_job_service import FinderJobService
    owner_id = database.get_db().execute("SELECT id FROM users WHERE email='reader@example.com'").fetchone()[0]
    job = FinderJobService().get(job_id, owner_id)
    first_item = job["items"][0]
    valid = first_item["candidates"][0]["url"]
    rejected = client.post(f"{job_url}/save", data={"item_id": first_item["id"], "urls": [valid, "https://evil.example/forged"]}, follow_redirects=False)
    assert "error=" in rejected.headers["location"]
    saved = client.post(f"{job_url}/save", data={"item_id": first_item["id"], "urls": valid, "credit_mode": "anonymous"}, follow_redirects=False)
    assert saved.status_code == 303 and "saved=1" in saved.headers["location"]
    assert "The Analects" in client.get("/library/my").text
    note = database.get_db().execute("SELECT note FROM book_submissions ORDER BY created_at DESC LIMIT 1").fetchone()[0]
    assert "Publication credit: anonymous" in note


def test_batch_finder_cancel_keeps_completed_results(client, monkeypatch):
    from app.services import finder_job_service
    _register(client)
    created = client.post("/library/find", data={"books": "One — Author\nTwo — Author"}, follow_redirects=False)
    job_url = created.headers["location"]
    async def fake_find(title, author):
        return [{"title": title, "url": "https://example.org/book.pdf", "viewable": True, "score": 80}]
    monkeypatch.setattr(finder_job_service, "find_readings", fake_find)
    assert client.post(f"{job_url}/next").json()["completed"] == 1
    assert client.post(f"{job_url}/cancel", follow_redirects=False).status_code == 303
    page = client.get(job_url)
    assert "cancelled" in page.text.lower() and "One" in page.text
    assert client.post(f"{job_url}/next").json()["status"] == "cancelled"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    from app.db import database

    if database._sqlite_connection is not None:
        database._sqlite_connection.close()
    database._sqlite_connection = None
    monkeypatch.setattr(settings, "DB_PATH", tmp_path / "alexandria-test.db")
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "SUPABASE_URL", None)
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_ROLE_KEY", None)
    monkeypatch.setattr(settings, "ENV", "development")
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", None)
    monkeypatch.setattr(settings, "GOOGLE_AUTH_ENABLED", False)
    with TestClient(app) as test_client:
        yield test_client
    if database._sqlite_connection is not None:
        database._sqlite_connection.close()
    database._sqlite_connection = None


def _register(client: TestClient) -> None:
    response = client.post(
        "/auth/register",
        data={
            "email": "reader@example.com",
            "password": "a-good-password",
            "display_name": "Reader",
            "next": "/library/my",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/library/my"


def test_guest_sees_a_preview_and_is_asked_to_sign_in_to_read(client: TestClient):
    book = CatalogService().get_books(limit=1)[0]

    home = client.get("/")
    catalog = client.get("/library")
    detail = client.get(f"/library/book/{book['id']}")
    reader = client.get(f"/read/{book['id']}", follow_redirects=False)

    assert home.status_code == 200
    assert "LibXNDR" in home.text
    assert "Waleed's Library" in home.text
    assert catalog.status_code == 200
    # Visitors get a look inside, not the whole shelf; the full collection opens on sign-in.
    assert "A look inside" in catalog.text and "Sign in to browse all 416 books" in catalog.text
    assert 'class="alphabet-jump"' not in catalog.text and 'By author' not in catalog.text
    assert 'class="topbar-search"' not in catalog.text
    assert 0 < catalog.text.count('class="book-tile"') <= 30
    assert 'id="random-book"' in catalog.text
    # The eye is reachable from the top bar, explained once on the landing page, and never a nav word.
    assert 'class="topbar-eye"' in catalog.text and "Eye of Alexandria" in catalog.text
    assert "Find books" not in catalog.text
    assert detail.status_code == 200
    assert book["title"] in detail.text
    assert "Sign in to read" in detail.text and f'href="/read/{book["id"]}/pdf"' not in detail.text
    # Reading itself is for members.
    assert reader.status_code == 303 and reader.headers["location"] == f"/auth/login?next=/read/{book['id']}"
    assert client.get(f"/read/{book['id']}/pdf").status_code == 401
    assert client.post(f"/read/{book['id']}/progress", json={"page_number": 2, "page_count": 20}).status_code == 401
    assert client.post(f"/read/{book['id']}/highlights", json={"page_number": 2, "selected_text": "hello"}).status_code == 401

    _register(client)
    member = client.get("/library")
    assert 'class="alphabet-jump"' in member.text and 'By author' in member.text and "Browse A–Z" in member.text
    assert 'class="topbar-search"' in member.text
    assert client.get(f"/read/{book['id']}").status_code == 200


def test_catalog_normalizes_copy_suffixes_and_groups_editions():
    from app.services.catalog_normalization import canonicalize_book, group_editions

    first = canonicalize_book({"id": "one", "title": "1984", "author": "George Orwell V 1", "availability": "pdf_ready"})
    second = canonicalize_book({"id": "two", "title": "1984", "author": "George Orwell (2)", "availability": "pdf_ready"})
    works = group_editions([first, second])

    assert first["author"] == second["author"] == "George Orwell"
    assert first["source_author"] == "George Orwell V 1"
    assert first["work_id"] == second["work_id"]
    assert len(works) == 1
    assert works[0]["edition_count"] == 2
    assert {edition["id"] for edition in works[0]["editions"]} == {"one", "two"}


def test_real_catalog_has_stable_work_and_edition_counts():
    catalog = CatalogService()
    works = catalog.get_works()

    assert len(works) < catalog.get_book_count()
    assert sum(work["edition_count"] for work in works) == catalog.get_book_count()
    assert all(work["id"].startswith("work_") for work in works)


def test_staged_link_books_have_a_local_preview_but_are_not_public(client: TestClient):
    from app.services.catalog_service import CatalogService

    catalog = CatalogService()
    assert catalog.get_book_count() == 544
    preview_books = catalog.get_books(include_drafts=True)
    staged = [book for book in preview_books if book.get("availability") == "external_link"]
    assert len(staged) == 51
    book = staged[0]
    assert catalog.get_book(book["id"]) is None

    _register(client)  # the local preview is a member view like the rest of the shelf
    preview = client.get("/library?preview_links=1&kind=links")
    detail = client.get(f"/library/book/{book['id']}?preview_links=1")
    cover = client.get(f"/library/book/{book['id']}/cover")

    assert preview.status_code == 200
    assert "Private preview" in preview.text
    assert 'The collection · 51 books' in preview.text
    assert book["title"] in preview.text
    assert detail.status_code == 200
    assert "Open source" in detail.text
    assert "Rights review pending" in detail.text
    assert book["source_url"] in detail.text.replace("&amp;", "&")
    assert cover.status_code == 200
    assert cover.headers["content-type"].startswith("image/svg+xml")
    assert client.get(f"/library/book/{book['id']}").status_code == 404
    assert client.get(f"/read/{book['id']}").status_code == 404


def test_author_browse_groups_books_and_formats(client: TestClient):
    _register(client)  # browsing by author is a member view
    response = client.get("/library?browse=authors")
    assert response.status_code == 200
    assert 'class="author-index"' in response.text
    assert 'class="discovery-accordion"' not in response.text
    assert "PDF" in response.text


def test_duplicate_files_are_one_work_with_inspectable_editions(client: TestClient):
    _register(client)  # library search is a member view
    response = client.get("/library?search=1984")
    assert response.status_code == 200
    assert "1 book · 2 editions" in response.text
    assert response.text.count('class="book-tile"') == 1
    book = next(book for book in CatalogService().get_books(search="1984") if book["title"] == "1984")
    detail = client.get(f"/library/book/{book['id']}")
    assert detail.status_code == 200
    assert "Also available" in detail.text


def test_guest_can_try_source_finder_without_an_account(client: TestClient, monkeypatch):
    from app.routes import finder

    async def fake_find(title, author=""):
        assert title == "The Analects"
        assert author == "Confucius"
        return [{
            "title": "The Analects — public PDF",
            "url": "https://example.edu/analects.pdf",
            "final_url": "https://example.edu/analects.pdf",
            "domain": "example.edu",
            "page_count": 248,
            "score": 91,
            "viewable": True,
            "edition_fit": "book-like length",
            "reasons": ["PDF response", "institutional host"],
        }]

    finder._quick_find_times.clear()
    monkeypatch.setattr(finder, "find_readings", fake_find)
    page = client.get("/library/find")
    assert page.status_code == 200
    assert "fair-use, viewable PDF" in page.text and "not the library search" not in page.text
    assert "Sign in to use the eye" in page.text and 'id="quick-finder"' not in page.text
    assert client.post("/library/find/quick", json={"title": "The Analects", "author": "Confucius"}).status_code == 401
    _register(client)
    page = client.get("/library/find")
    assert 'id="quick-finder"' in page.text and 'id="contribute-form"' in page.text and "Send to Waleed" in page.text
    assert "Try it without an account" not in page.text and "Bring a book in" not in page.text
    response = client.post("/library/find/quick", json={"title": "The Analects", "author": "Confucius"})
    assert response.status_code == 200
    assert response.json()["results"][0]["url"] == "https://example.edu/analects.pdf"


def test_homepage_leads_with_living_collection_and_alexandria_identity(client: TestClient):
    page = client.get("/library")
    assert page.status_code == 200
    assert "Read what matters" not in page.text
    assert "Read anything you want." in page.text
    assert "books on the shelves" in page.text
    # The finder's old legal wording stays off every public page; the eye is the only door to it.
    assert "fair use" not in page.text and "Find a book" not in page.text
    assert page.text.count('href="/library/find"') == 1
    finder = client.get("/library/find").text
    assert "fair use" not in finder and "copyright" not in finder.lower() and "simply points you" not in finder
    assert "Why Alexandria?" in page.text
    assert "logo-cartouche" in page.text


def test_public_privacy_and_terms_explain_reader_data_and_submissions(client: TestClient):
    privacy = client.get("/privacy")
    terms = client.get("/terms")
    assert privacy.status_code == 200 and terms.status_code == 200
    assert "does not sell your personal information" in privacy.text
    assert "Reading memory is private to the reader" in privacy.text
    assert "Only upload a file when you are permitted" in terms.text
    assert "request review or removal" in terms.text


def test_book_record_offers_reader_and_direct_pdf(client: TestClient):
    book = CatalogService().get_books(limit=1)[0]
    _register(client)
    detail = client.get(f"/library/book/{book['id']}")
    assert f'href="/read/{book["id"]}"' in detail.text
    assert f'href="/read/{book["id"]}/pdf"' in detail.text
    assert "Open the PDF directly" in detail.text
    assert '<p class="preview-author">George Orwell</p>' in detail.text
    assert '<p class="preview-author">George Orwell V' not in detail.text
    # The shelf asks for the record alone and shows it in a dialog over the books.
    partial = client.get(f"/library/book/{book['id']}", headers={"X-Partial": "1"})
    assert partial.status_code == 200
    assert "<html" not in partial.text and 'class="preview"' in partial.text
    assert "NOTES (" not in detail.text  # no empty notebook tab in the preview


def test_signed_in_reader_can_submit_link_and_pdf_for_private_review(client: TestClient, tmp_path: Path):
    import fitz

    guest = client.get("/library/contribute", follow_redirects=False)
    assert guest.status_code == 303
    assert guest.headers["location"] == "/library/find#contribute"
    assert "Sign in to use the eye" in client.get("/library/find").text
    assert client.post("/library/contribute", data={"title": "A book", "links": "https://example.org/book.pdf"}, follow_redirects=False).status_code == 303

    _register(client)
    document = fitz.open()
    document.new_page()
    pdf = document.tobytes()
    document.close()
    response = client.post(
        "/library/contribute",
        data={"title": "A Good Book", "author": "A. Writer", "links": "https://example.org/book.pdf", "note": "Please review this edition."},
        files=[("files", ("good-book.pdf", pdf, "application/pdf"))],
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/library/find?submitted=1#contribute"
    pending = client.get(response.headers["location"])
    assert "Sent to Waleed" in pending.text
    assert "A Good Book" in pending.text
    assert "Waiting for Waleed" in pending.text
    assert CatalogService().get_book("A Good Book") is None

    invalid = client.post("/library/contribute", data={"title": "Private network", "links": "http://127.0.0.1/book.pdf"})
    assert invalid.status_code == 400
    assert "private network" in invalid.text.lower()


def test_source_finder_requires_account_and_returns_verified_leads(client: TestClient, monkeypatch):
    from app.routes import contributions

    assert client.post("/library/contribute/find", json={"title": "Dune"}).status_code == 401
    _register(client)
    monkeypatch.setattr(settings, "SOURCE_FINDER_ENABLED", True)

    async def fake_find(title, author):
        assert (title, author) == ("Dune", "Frank Herbert")
        return [
            {"title": "Dune PDF", "url": "https://books.example/original", "final_url": "https://books.example/dune.pdf", "domain": "books.example", "page_count": 512, "score": 88, "viewable": True},
            {"title": "Buy Dune", "url": "https://store.example/dune", "viewable": False},
        ]

    monkeypatch.setattr(contributions, "find_readings", fake_find)
    found = client.post("/library/contribute/find", json={"title": "Dune", "author": "Frank Herbert"})
    assert found.status_code == 200
    assert len(found.json()["results"]) == 1
    assert found.json()["results"][0]["url"] == "https://books.example/dune.pdf"


def test_production_never_loads_staged_links(client: TestClient, monkeypatch):
    catalog = CatalogService()
    staged_id = next(
        book["id"] for book in catalog.get_books(include_drafts=True)
        if book.get("availability") == "external_link"
    )
    monkeypatch.setattr(settings, "ENV", "production")
    assert catalog.get_book(staged_id, include_drafts=True) is None
    assert client.get(f"/library/book/{staged_id}?preview_links=1").status_code == 404
    assert client.get(f"/library/book/{staged_id}/cover").status_code == 404


def test_link_approval_is_individual_and_explicit(tmp_path: Path, monkeypatch):
    from admin import approve_link_books

    output = tmp_path / "approved.json"
    monkeypatch.setattr(approve_link_books, "PUBLIC_PATH", output)
    approved = approve_link_books.approve(["Dracula"])
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert len(approved) == payload["book_count"] == 1
    assert payload["books"][0]["title"] == "Dracula"
    assert payload["books"][0]["rights_status"] == "approved"
    assert payload["books"][0]["visibility"] == "public"
    with pytest.raises(ValueError):
        approve_link_books.approve(["Not a staged book"])
    assert json.loads(output.read_text(encoding="utf-8"))["book_count"] == 1


def test_registered_reader_can_save_progress_highlight_note_and_chat(client: TestClient):
    book = CatalogService().get_books(limit=1)[0]
    _register(client)

    reader = client.get(f"/read/{book['id']}")
    progress = client.post(
        f"/read/{book['id']}/progress",
        json={"page_number": 12, "page_count": 120},
    )
    highlight = client.post(
        f"/read/{book['id']}/highlights",
        json={
            "page_number": 12,
            "selected_text": "Freedom is the freedom to say that two plus two make four.",
            "color": "gold",
            "text_start": 10,
            "text_end": 68,
        },
    )
    highlight_id = highlight.json()["highlight"]["id"]
    note = client.post(
        f"/read/{book['id']}/highlights/{highlight_id}/note",
        json={"text": "Truth as a condition of political freedom."},
    )
    chat = client.post(
        f"/read/{book['id']}/highlights/{highlight_id}/chat",
        json={"question": "What does this mean?"},
    )
    board = client.get("/library/my")
    memory = client.get("/library/my/memory")

    assert reader.status_code == 200
    assert progress.status_code == 200
    assert progress.json()["progress"]["percent"] == 10.0
    assert highlight.status_code == 200
    assert note.status_code == 200
    assert chat.status_code == 200
    assert len(chat.json()["messages"]) == 2
    assert board.status_code == 200
    assert "Reading board" in board.text
    assert book["title"] in board.text
    assert memory.status_code == 200
    assert "Freedom is the freedom" in memory.text
    assert "Truth as a condition" in memory.text


def test_reading_companion_is_private_persistent_filtered_and_cites_memory(client: TestClient, monkeypatch):
    book = CatalogService().get_books(limit=1)[0]
    monkeypatch.setattr(settings, "USE_MOCK_AGENTS", True)
    _register(client)
    highlight = client.post(
        f"/read/{book['id']}/highlights",
        json={"page_number": 7, "selected_text": "Power survives when people cannot name the truth."},
    ).json()["highlight"]
    client.post(
        f"/read/{book['id']}/highlights/{highlight['id']}/note",
        json={"text": "Naming is part of resistance."},
    )

    answer = client.post(
        "/library/my/memory/chat",
        json={"question": "What does my reading say about power and truth?"},
    )
    assert answer.status_code == 200
    message = answer.json()["message"]
    assert message["role"] == "assistant"
    assert message["sources"][0]["highlight_id"] == highlight["id"]
    assert message["sources"][0]["url"].endswith(f"#highlight-{highlight['id']}")
    assert "quote" not in message["sources"][0]

    memory = client.get("/library/my/memory")
    assert "What does my reading say" in memory.text
    assert "retrieval-only" in memory.text.lower()
    assert book["title"] in memory.text
    assert "Power survives" in client.get("/library/my/memory?q=Power").text
    assert "No passage matches" in client.get("/library/my/memory?q=unfindable-phrase").text

    _switch_reader(client, "private-other@example.com")
    other_memory = client.get("/library/my/memory")
    assert "What does my reading say" not in other_memory.text
    empty_answer = client.post("/library/my/memory/chat", json={"question": "What have I saved?"})
    assert empty_answer.status_code == 200
    assert empty_answer.json()["message"]["sources"] == []


def test_shelf_status_is_saved_without_faking_or_erasing_page_progress(client: TestClient):
    book = CatalogService().get_books(limit=1)[0]
    _register(client)
    service = UserService()

    empty = client.get("/library/my")
    assert "Start with a book you want to keep" in empty.text
    saved = client.post(f"/library/save/{book['id']}", follow_redirects=False)
    assert saved.status_code == 303
    from app.db.database import get_db
    reader_id = get_db().execute("SELECT id FROM users WHERE email = ?", ("reader@example.com",)).fetchone()["id"]
    assert service.get_reading_status(reader_id, book["id"]) == "want_to_read"
    assert service.get_progress(reader_id, book["id"]) is None

    read = client.post(
        f"/library/book/{book['id']}/status",
        data={"status": "read", "next": "/library/my"},
        follow_redirects=False,
    )
    assert read.status_code == 303
    assert read.headers["location"] == "/library/my"
    assert service.get_reading_status(reader_id, book["id"]) == "read"
    assert service.get_progress(reader_id, book["id"]) is None

    client.post(f"/read/{book['id']}/progress", json={"page_number": 5, "page_count": 100})
    assert service.get_reading_status(reader_id, book["id"]) == "read"
    assert service.get_progress(reader_id, book["id"])["percent"] == 5.0
    client.post(f"/library/book/{book['id']}/status", data={"status": "want_to_read"})
    assert service.get_reading_status(reader_id, book["id"]) == "want_to_read"
    assert service.get_progress(reader_id, book["id"])["percent"] == 5.0

    client.post("/auth/logout", follow_redirects=False)
    login = client.post(
        "/auth/login",
        data={"email": "reader@example.com", "password": "a-good-password"},
        follow_redirects=False,
    )
    assert login.status_code == 303
    board = client.get("/library/my")
    assert book["title"] in board.text
    assert 'class="reading-lane lane-want_to_read"' in board.text


def test_real_progress_moves_want_to_read_into_reading_only(client: TestClient):
    book = CatalogService().get_books(limit=1)[0]
    _register(client)
    from app.db.database import get_db
    reader_id = get_db().execute("SELECT id FROM users WHERE email = ?", ("reader@example.com",)).fetchone()["id"]
    service = UserService()
    client.post(f"/library/save/{book['id']}")
    client.post(f"/read/{book['id']}/progress", json={"page_number": 1, "page_count": 100})
    assert service.get_reading_status(reader_id, book["id"]) == "want_to_read"
    client.post(f"/read/{book['id']}/progress", json={"page_number": 2, "page_count": 100})
    assert service.get_reading_status(reader_id, book["id"]) == "reading"
    client.post(f"/library/book/{book['id']}/status", data={"status": "read"})
    client.post(f"/read/{book['id']}/progress", json={"page_number": 3, "page_count": 100})
    assert service.get_reading_status(reader_id, book["id"]) == "read"


def test_existing_sqlite_shelf_migrates_without_losing_progress(tmp_path: Path, monkeypatch):
    from app.db import database

    old_db = tmp_path / "existing.db"
    connection = sqlite3.connect(old_db)
    connection.executescript("""
        CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL DEFAULT '', display_name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE saved_books (id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
            book_id TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, book_id));
        CREATE TABLE reading_progress (user_id TEXT NOT NULL, book_id TEXT NOT NULL,
            page_number INTEGER NOT NULL DEFAULT 1, page_count INTEGER, percent REAL NOT NULL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (user_id, book_id));
        INSERT INTO users (id,email,display_name) VALUES ('u1','a@example.org','A');
        INSERT INTO saved_books (id,user_id,book_id) VALUES ('s1','u1','book-1');
        INSERT INTO reading_progress (user_id,book_id,page_number,page_count,percent)
            VALUES ('u1','book-1',40,100,40);
    """)
    connection.close()
    if database._sqlite_connection is not None:
        database._sqlite_connection.close()
    database._sqlite_connection = None
    monkeypatch.setattr(settings, "DB_PATH", old_db)
    monkeypatch.setattr(settings, "SUPABASE_URL", None)
    monkeypatch.setattr(settings, "SUPABASE_SERVICE_ROLE_KEY", None)
    database.init_db()
    assert UserService().get_reading_status("u1", "book-1") == "reading"
    assert UserService().get_progress("u1", "book-1")["percent"] == 40
    database.init_db()
    assert UserService().get_reading_status("u1", "book-1") == "reading"
    database._sqlite_connection.close()
    database._sqlite_connection = None


def test_device_pairing_and_api_serve_the_kindle(client: TestClient, monkeypatch):
    from app.routes import device_api

    # The device asks for a code; nobody is signed in on it.
    issued = client.post("/api/v1/device/code", json={"device_name": "Kindle Scribe"})
    assert issued.status_code == 200
    code, secret = issued.json()["code"], issued.json()["secret"]
    assert len(code) == 6 and issued.json()["claim_url"].endswith("/device")
    assert client.get("/api/v1/device/poll", params={"code": code, "secret": secret}).json()["status"] == "pending"
    assert client.get("/api/v1/device/poll", params={"code": code, "secret": "wrong"}).json()["status"] == "expired"
    assert client.get("/api/v1/me").status_code == 401
    assert client.get("/device", follow_redirects=False).status_code == 303

    # The reader claims it from a browser.
    _register(client)
    page = client.get(f"/account/devices?code={code[:3]}-{code[3:].lower()}")
    assert page.status_code == 200 and "Kindle Scribe" in page.text
    assert client.post("/account/devices", data={"code": f"{code[:3]}-{code[3:]}"}, follow_redirects=False).headers["location"] == "/account/devices?done=1"
    client.cookies.clear()

    # The device collects its token exactly once.
    answer = client.get("/api/v1/device/poll", params={"code": code, "secret": secret}).json()
    assert answer["status"] == "claimed" and answer["token"]
    assert client.get("/api/v1/device/poll", params={"code": code, "secret": secret}).json()["status"] == "expired"
    headers = {"Authorization": f"Bearer {answer['token']}"}

    me = client.get("/api/v1/me", headers=headers).json()
    assert me["user"]["display_name"] and me["collection"] >= 400
    found = client.get("/api/v1/search", params={"q": "1984"}, headers=headers).json()["results"]
    assert found and found[0]["title"] == "1984" and found[0]["availability"] == "pdf"
    book = found[0]
    assert client.post("/api/v1/progress", json={"book_id": book["id"], "page_number": 12, "page_count": 300}, headers=headers).json()["progress"]["percent"] == 4.0
    shelf = client.get("/api/v1/library", headers=headers).json()["books"]
    assert shelf[0]["id"] == book["id"] and shelf[0]["reading_status"] == "reading" and shelf[0]["page_number"] == 12
    assert client.post(f"/api/v1/books/{book['id']}/status", json={"status": "read"}, headers=headers).json()["status"] == "read"
    assert client.get(f"/api/v1/books/{book['id']}", headers=headers).json()["book"]["reading_status"] == "read"
    assert client.post("/api/v1/progress", json={"book_id": "nope", "page_number": 1, "page_count": 1}, headers=headers).status_code == 404

    # The Eye through the device: same finder, same limits, proxied downloads with the same checks.
    async def fake_find(title, author):
        return [{"title": "Dune PDF", "url": "https://books.example/dune.pdf", "final_url": "https://books.example/dune.pdf",
                 "domain": "books.example", "page_count": 512, "score": 88, "viewable": True}]
    monkeypatch.setattr(device_api, "find_readings", fake_find)
    monkeypatch.setattr(settings, "SOURCE_FINDER_ENABLED", True)
    device_api._eye_times.clear()
    eye = client.post("/api/v1/eye", json={"title": "Dune", "author": "Frank Herbert"}, headers=headers).json()
    assert eye["results"][0]["url"] == "https://books.example/dune.pdf"
    assert client.get("/api/v1/eye/fetch", params={"url": "https://cdn.bookey.app/x.pdf"}, headers=headers).status_code == 400
    assert client.get("/api/v1/eye/fetch", params={"url": "http://127.0.0.1/x.pdf"}, headers=headers).status_code == 400
    sent = client.post("/api/v1/contribute", json={"title": "Dune", "author": "Frank Herbert", "links": ["https://books.example/dune.pdf"]}, headers=headers)
    assert sent.status_code == 200 and sent.json()["status"] == "pending"
