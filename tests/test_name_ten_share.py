"""Name Ten part 4: share links, the public result page and the card images."""

from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

from test_name_ten_play import ANON, _ten, ten  # noqa: F401  (fixtures)
from test_library_app import client  # noqa: F401

OTHER = "1c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e5f"


def _play(ten: TestClient, prefix="S") -> dict:
    return ten.post("/ten/play", json={"game_id": 0, "anon_id": ANON, "items": _ten(prefix)}).json()


def test_nothing_is_public_until_the_player_shares(ten: TestClient):
    play = _play(ten)
    assert ten.post(f"/ten/play/{play['play_id']}/share", json={"anon_id": OTHER}).status_code == 404
    first = ten.post(f"/ten/play/{play['play_id']}/share", json={"anon_id": ANON}).json()
    again = ten.post(f"/ten/play/{play['play_id']}/share", json={"anon_id": ANON}).json()
    assert first["url"] == again["url"] and "/ten/p/" in first["url"]
    assert first["x_intent"].startswith("https://x.com/intent/post?")

    slug = first["url"].rsplit("/", 1)[1]
    page = ten.get(f"/ten/p/{slug}")
    assert page.status_code == 200
    assert "S Book 7" in page.text
    assert f'content="{first["url"]}/card.png"' in page.text
    assert "twitter:card" in page.text
    assert ten.get("/ten/p/notarealslug").status_code == 404


def test_cards_render_at_both_sizes(ten: TestClient):
    play = _play(ten, "A rather long title that will certainly need to be cut short somewhere")
    url = ten.post(f"/ten/play/{play['play_id']}/share", json={"anon_id": ANON}).json()["url"]
    slug = url.rsplit("/", 1)[1]
    wide = ten.get(f"/ten/p/{slug}/card.png")
    tall = ten.get(f"/ten/p/{slug}/card.png", params={"size": "tall"})
    assert wide.headers["content-type"] == "image/png"
    assert Image.open(BytesIO(wide.content)).size == (1200, 630)
    assert Image.open(BytesIO(tall.content)).size == (1080, 1350)
