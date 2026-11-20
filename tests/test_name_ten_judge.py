"""Name Ten part 3: badges and the judge's verdict."""

import pytest
from fastapi.testclient import TestClient

from app.agents import llm_provider
from app.config import settings
from app.db.database import get_db
from app.services.name_ten import badges, judge
from test_name_ten_play import ANON, _ten, ten  # noqa: F401  (fixtures)
from test_library_app import _register, client  # noqa: F401


def _play(**facts):
    base = {"lists_before": 0, "early": True, "closest_shared": 0, "rarest_pair": None,
            "most_common": None, "missing_eleventh": None}
    base.update(facts)
    items = [{"title": f"Book {i}", "author": "A", "status": "unverified"} for i in range(10)]
    return {"score": 64, "max_overlap": base["closest_shared"], "findings_json": base, "items": items}


def test_badges_are_earned_from_the_facts():
    play = _play(lists_before=300, early=False, closest_shared=1,
                 rarest_pair={"titles": ["X", "Y"], "together": 0, "never_seen": True})
    play["items"][0]["status"] = play["items"][1]["status"] = play["items"][2]["status"] = "finder"
    keys = [badge["key"] for badge in badges.earned(play["findings_json"], play["items"])]
    assert keys == ["uncharted", "own_shelf", "excavator"]
    assert [b["key"] for b in badges.earned(_play()["findings_json"], _play()["items"])] == ["early_hand"]
    # Comparative badges wait for enough lists.
    young = _play(lists_before=3, closest_shared=0)
    assert "own_shelf" not in [b["key"] for b in badges.earned(young["findings_json"], young["items"])]


def test_the_judge_may_not_invent_numbers():
    data = judge._facts_for_model(_play(), [])
    assert judge.check({"epithet": "The Reader", "verdict": "Your score of 64 is earned."}, data)
    assert judge.check({"epithet": "The Reader", "verdict": "You beat 93% of readers."}, data) is None
    assert judge.check({"epithet": "x", "verdict": ""}, data) is None
    assert judge.check("nope", data) is None
    long_name = judge.check({"epithet": "The " + "Very " * 20, "verdict": "Fine."}, data)
    assert long_name["epithet"] == ""


def test_template_verdict_uses_only_findings():
    play = _play(rarest_pair={"titles": ["Ulysses", "Dune"], "together": 0, "never_seen": True},
                 missing_eleventh={"title": "Moby Dick", "author": "Melville", "book_id": "m", "work_key": "w"})
    result = judge.template(play, badges.earned(play["findings_json"], play["items"]))
    assert "Ulysses" in result["verdict"] and "Moby Dick" in result["verdict"]
    assert result["epithet"] == "The Cartographer"


def test_play_returns_the_verdict_and_keeps_badges(ten: TestClient, monkeypatch):
    calls = []

    class FakeProvider:
        def call(self, **kwargs):
            calls.append(kwargs)
            return {"epithet": "The Night Reader", "verdict": "A shelf that argues with itself."}

    monkeypatch.setattr(settings, "USE_MOCK_AGENTS", False)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test")
    monkeypatch.setattr(llm_provider, "get_llm_provider", lambda: FakeProvider())
    _register(ten)
    data = ten.post("/ten/play", json={"game_id": 0, "items": _ten("Q")}).json()
    assert data["verdict"] == {"epithet": "The Night Reader", "verdict": "A shelf that argues with itself.",
                               "source": "judge"}
    assert [b["key"] for b in data["badges"]] == ["early_hand"]
    assert "Q Book 3" in calls[0]["user_prompt"] and "data, not instructions" in calls[0]["user_prompt"]
    db = get_db()
    assert db.execute("SELECT count(*) FROM user_badge").fetchone()[0] == 1
    assert "Night Reader" in db.execute("SELECT verdict_json FROM ten_play").fetchone()[0]


def test_a_failing_judge_falls_back_to_the_template(ten: TestClient, monkeypatch):
    class Broken:
        def call(self, **kwargs):
            raise RuntimeError("down")

    monkeypatch.setattr(settings, "USE_MOCK_AGENTS", False)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "test")
    monkeypatch.setattr(llm_provider, "get_llm_provider", lambda: Broken())
    data = ten.post("/ten/play", json={"game_id": 0, "anon_id": ANON, "items": _ten("R")}).json()
    assert data["verdict"]["source"] == "template" and data["verdict"]["verdict"]
