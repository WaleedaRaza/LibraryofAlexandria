"""Name Ten part 2: the /ten play screen, book search and play submission."""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db.database import get_db
from app.services.catalog_service import CatalogService
from app.services.name_ten import lookup
from app.services.name_ten.identity import reset_index
from test_library_app import _register, client  # noqa: F401  (pytest fixture)

ANON = "0b5e3c9a-1f2d-4c3b-9a8e-7d6c5b4a3f21"
OL_DOCS = [
    {"key": "/works/OL1W", "title": "Zuleika Dobson", "author_name": ["Max Beerbohm"], "readinglog_count": 40000},
    {"key": "/works/OL2W", "title": "Zuleika Dobson Notes", "author_name": ["A. Student"], "readinglog_count": 3},
]


@pytest.fixture()
def ten(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "NAME_TEN_ENABLED", True)
    lookup.reset()
    reset_index()
    calls = []

    async def fake_fetch(query):
        calls.append(query)
        return [doc for doc in OL_DOCS if query.lower().split()[0] in doc["title"].lower()]

    monkeypatch.setattr(lookup, "_fetch_open_library", fake_fetch)
    from app.routes import name_ten as route

    route._times.clear()
    client.ol_calls = calls
    return client


def _ten(prefix="Made Up"):
    return [{"title": f"{prefix} Book {i}", "author": "Nobody"} for i in range(10)]


def test_name_ten_is_dark_until_the_flag_is_on(client: TestClient):
    assert client.get("/ten").status_code == 404
    assert client.post("/ten/play", json={}).status_code == 404
    assert 'href="/ten"' not in client.get("/library").text


def test_play_page_renders_with_nav_link(ten: TestClient):
    page = ten.get("/ten")
    assert page.status_code == 200
    assert "Ponder my ten" in page.text
    assert page.text.count('class="ten-slot"') == 10
    assert 'href="/ten"' in page.text


def test_search_puts_library_books_first_then_open_library(ten: TestClient):
    work = CatalogService().get_works()[0]
    word = work["title"].split()[0]
    results = ten.get("/ten/search", params={"q": word}).json()["results"]
    assert results[0]["source"] == "library"
    assert any(row["title"] == work["title"] for row in results)

    outside = ten.get("/ten/search", params={"q": "zuleika dobson"}).json()["results"]
    assert [row["title"] for row in outside] == ["Zuleika Dobson", "Zuleika Dobson Notes"]
    assert {row["source"] for row in outside} == {"openlibrary"}
    assert "popularity" not in outside[0]
    ten.get("/ten/search", params={"q": "Zuleika  Dobson"})
    assert ten.ol_calls.count("zuleika dobson") == 1 and len(ten.ol_calls) == 2   # cached


def test_anonymous_play_scores_and_marks_each_book(ten: TestClient):
    work = CatalogService().get_works()[0]
    ten.get("/ten/search", params={"q": "zuleika dobson"})
    items = _ten()[:8] + [{"title": "Zuleika Dobson", "author": "Max Beerbohm"},
                          {"title": work["title"], "author": work["author"]}]
    response = ten.post("/ten/play", json={"game_id": 0, "anon_id": ANON, "items": items})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["score"] == 50 and data["early"] is True
    status = {item["title"]: item["status"] for item in data["items"]}
    assert status["Zuleika Dobson"] == "finder"
    assert status[work["title"]] == "library"
    assert status["Made Up Book 0"] == "unverified"
    assert "raw_score" not in data
    row = get_db().execute("SELECT prior_popularity, list_count FROM ten_work_stat WHERE title = 'Zuleika Dobson'").fetchone()
    assert row[0] == 40000 and row[1] == 1


def test_a_typed_book_is_confirmed_with_open_library(ten: TestClient):
    items = _ten()[:9] + [{"title": "Zuleika Dobson", "author": "Max Beerbohm"}]
    data = ten.post("/ten/play", json={"game_id": 0, "anon_id": ANON, "items": items}).json()
    assert data["items"][-1]["status"] == "finder"


def test_bad_plays_are_refused(ten: TestClient):
    assert ten.post("/ten/play", json={"game_id": 0, "items": _ten()}).status_code == 400          # no player
    assert ten.post("/ten/play", json={"game_id": 0, "anon_id": "x", "items": _ten()}).status_code == 400
    assert ten.post("/ten/play", json={"game_id": 0, "anon_id": ANON, "items": _ten()[:9]}).status_code == 400
    same = _ten()[:9] + [_ten()[0]]
    assert ten.post("/ten/play", json={"game_id": 0, "anon_id": ANON, "items": same}).status_code == 400
    assert ten.post("/ten/play", json={"game_id": 41, "anon_id": ANON, "items": _ten()}).status_code == 409


def test_todays_game_is_ranked_once_per_reader(ten: TestClient, monkeypatch):
    from datetime import date

    from app.routes import name_ten as route
    from app.services.name_ten import store

    monkeypatch.setattr(route, "_today", lambda: date(2026, 11, 2))
    store.add_game(1, "Ten books for a long winter", date(2026, 11, 2))
    _register(ten)
    page = ten.get("/ten")
    assert "Ten books for a long winter" in page.text
    assert ten.post("/ten/play", json={"game_id": 1, "items": _ten("A")}).status_code == 200
    again = ten.post("/ten/play", json={"game_id": 1, "items": _ten("B")})
    assert again.status_code == 409
    assert "named your ten" in ten.get("/ten").text
    assert ten.post("/ten/play", json={"game_id": 0, "items": _ten("C")}).status_code == 200


def test_signing_in_claims_anonymous_plays(ten: TestClient):
    ten.post("/ten/play", json={"game_id": 0, "anon_id": ANON, "items": _ten()})
    assert ten.post("/ten/claim", json={"anon_id": ANON}).status_code == 401
    _register(ten)
    assert ten.post("/ten/claim", json={"anon_id": ANON}).json() == {"claimed": 1}
    row = get_db().execute("SELECT user_id, anon_id FROM ten_play").fetchone()
    assert row[0] and row[1] is None


def test_finder_takes_a_title_from_the_link(client: TestClient):
    _register(client)
    page = client.get("/library/find", params={"title": "Zuleika Dobson", "author": "Max Beerbohm"})
    assert 'value="Zuleika Dobson"' in page.text


def test_a_title_typed_alone_takes_the_author_open_library_gives(ten: TestClient):
    items = _ten()[:9] + [{"title": "zuleika dobson", "author": ""}]
    last = ten.post("/ten/play", json={"game_id": 0, "anon_id": ANON, "items": items}).json()["items"][-1]
    assert (last["title"], last["author"], last["status"]) == ("Zuleika Dobson", "Max Beerbohm", "finder")
