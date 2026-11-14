"""Name Ten part 5: keeping a ten, the public reader page, and the Finder hand-off."""

from fastapi.testclient import TestClient

from app.config import settings
from app.services.catalog_service import CatalogService
from test_name_ten_play import ANON, _ten, ten  # noqa: F401  (fixtures)
from test_library_app import _register, client  # noqa: F401


def _signed_in_play(ten: TestClient, items=None) -> dict:
    _register(ten)
    ten.post("/account", data={"display_name": "Reader", "username": "reader.one"})
    return ten.post("/ten/play", json={"game_id": 0, "items": items or _ten("K")}).json()


def test_keeping_a_ten_makes_a_public_page(ten: TestClient):
    work = CatalogService().get_works()[0]
    play = _signed_in_play(ten, _ten("K")[:9] + [{"title": work["title"], "author": work["author"]}])
    assert ten.get("/u/reader.one").status_code == 404           # nothing public before keeping
    assert ten.post(f"/ten/play/{play['play_id']}/keep").json() == {"profile": "/u/reader.one"}
    page = ten.get("/u/reader.one")
    assert page.status_code == 200 and "K Book 4" in page.text and "Early hand" in page.text
    assert "named" in page.text                                    # the owner sees proof marks
    account = ten.get("/account")
    assert "Your ten" in account.text and "/u/reader.one" in account.text


def test_strangers_see_the_ten_but_not_reading_activity(ten: TestClient):
    play = _signed_in_play(ten)
    ten.post(f"/ten/play/{play['play_id']}/keep")
    ten.post("/auth/logout")
    page = ten.get("/u/reader.one")
    assert page.status_code == 200 and "K Book 1" in page.text
    assert "ten-proof" not in page.text


def test_only_the_player_can_keep_or_find(ten: TestClient):
    anon = ten.post("/ten/play", json={"game_id": 0, "anon_id": ANON, "items": _ten("Z")}).json()
    assert ten.post(f"/ten/play/{anon['play_id']}/keep").status_code == 401
    _register(ten)
    assert ten.post(f"/ten/play/{anon['play_id']}/keep").status_code == 404


def test_missing_books_go_to_the_finder_as_one_run(ten: TestClient, monkeypatch):
    created = []

    def fake_create(self, user_id, books):
        created.append(books)
        return "job_123"

    from app.services import finder_job_service

    monkeypatch.setattr(finder_job_service.FinderJobService, "create", fake_create)
    play = _signed_in_play(ten)
    assert ten.post(f"/ten/play/{play['play_id']}/find").json() == {"job": "/library/find/job_123"}
    assert len(created[0]) == 10 and created[0][0]["title"] == "K Book 0"


def test_profiles_are_dark_with_the_flag_off(client: TestClient):
    assert not settings.NAME_TEN_ENABLED
    assert client.get("/u/anyone").status_code == 404
