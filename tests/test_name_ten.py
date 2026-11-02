"""Name Ten part 1: identity, combo uniqueness scoring, findings and storage."""

import random

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.services import name_ten
from app.services.catalog_service import CatalogService
from app.services.name_ten import findings, scoring, store
from app.services.name_ten.identity import reset_index, resolve, work_key
from test_library_app import client  # noqa: F401  (pytest fixture)

KEYS = [f"work_{i:02d}" for i in range(10)]


def _items(prefix: str, count: int = 10, start: int = 0) -> list[dict]:
    return [resolve(f"{prefix} {i}", "Some Author", verified=True) for i in range(start, start + count)]


# --- pure scoring -----------------------------------------------------------

def test_order_does_not_matter():
    counts = {key: 40 + i for i, key in enumerate(KEYS)}
    pairs = {(KEYS[0], KEYS[1]): 30, (KEYS[2], KEYS[5]): 2}
    shuffled = KEYS[:]
    random.Random(4).shuffle(shuffled)
    assert scoring.combo_raw(KEYS, 1000, counts, {}, pairs, 3) == pytest.approx(
        scoring.combo_raw(shuffled, 1000, counts, {}, pairs, 3)
    )
    assert scoring.combo_hash(KEYS) == scoring.combo_hash(shuffled)


def test_a_list_must_be_ten_different_books():
    with pytest.raises(ValueError):
        scoring.ordered_keys(KEYS[:9])
    with pytest.raises(ValueError):
        scoring.ordered_keys(KEYS[:9] + [KEYS[0]])


def test_a_pair_with_no_history_scores_about_zero():
    assert scoring.pair_surprise("a", "b", 5000, {}, {}, {}) == pytest.approx(0.0, abs=0.01)
    # Two books each on 1 list in 5,000 are not expected together either.
    assert abs(scoring.pair_surprise("a", "b", 5000, {"a": 1, "b": 1}, {}, {})) < 0.01


def test_unpaired_bestsellers_beat_unknown_books():
    n = 1000
    famous = {key: 300 for key in KEYS}            # each on 30% of lists, never together
    unpaired_bestsellers = scoring.combo_raw(KEYS, n, famous, {}, {}, 0)
    unknown = scoring.combo_raw(KEYS, n, {}, {}, {}, 0)
    assert unpaired_bestsellers > unknown + 1


def test_books_usually_named_together_score_below_chance():
    n = 1000
    counts = {key: 300 for key in KEYS}
    always_together = {(a, b): 300 for i, a in enumerate(KEYS) for b in KEYS[i + 1:]}
    assert scoring.combo_raw(KEYS, n, counts, {}, always_together, 0) < scoring.combo_raw(KEYS, n, {}, {}, {}, 0)


def test_copying_an_earlier_list_costs_points():
    fresh = scoring.combo_raw(KEYS, 100, {}, {}, {}, 0)
    copied = scoring.combo_raw(KEYS, 100, {}, {}, {}, 10)
    assert fresh - copied == pytest.approx(10 * scoring.LAMBDA)


def test_percentile_score_bounds_and_ties():
    assert scoring.percentile_score(0, 0, 0) == 50
    assert scoring.percentile_score(97, 0, 100) == 97
    assert scoring.percentile_score(0, 2, 2) == 50
    assert scoring.percentile_score(5, 0, 5) == 100


def test_prior_grows_with_popularity_and_is_bounded():
    assert scoring.prior(None) == scoring.DEFAULT_PRIOR
    assert scoring.prior(0) == 0.0005
    assert scoring.prior(10) < scoring.prior(10_000) <= 0.05


def test_findings_name_the_rarest_pair_and_most_common_pick():
    items = [{"work_key": key, "title": f"Title {key}", "status": "finder"} for key in KEYS]
    counts = {key: 20 for key in KEYS}
    counts[KEYS[3]] = 500
    pairs = {(a, b): 5 for i, a in enumerate(KEYS) for b in KEYS[i + 1:]}
    pairs[(KEYS[3], KEYS[7])] = 0
    facts = findings.compute(items, n_lists=1000, work_counts=counts, priors={}, pair_counts=pairs,
                             max_overlap=4, co_named=[], library_book=lambda key: None)
    assert facts["most_common"] == {"title": f"Title {KEYS[3]}", "lists": 500, "one_in": 2}
    assert sorted(facts["rarest_pair"]["titles"]) == sorted([f"Title {KEYS[3]}", f"Title {KEYS[7]}"])
    assert facts["rarest_pair"]["never_seen"] is True
    assert facts["closest_shared"] == 4


# --- identity ---------------------------------------------------------------

def test_typed_titles_share_the_catalog_work_key(client: TestClient):
    reset_index()
    work = CatalogService().get_works()[0]
    picked = resolve(f"  {work['title'].upper()} ", work["author"])
    assert picked["status"] == "library"
    assert picked["work_key"] == work["id"]
    assert picked["book_id"]
    assert resolve("A Book Nobody Wrote", "Nobody")["status"] == "unverified"
    assert resolve("A Book Nobody Wrote", "Nobody", verified=True)["status"] == "finder"
    assert work_key("The Republic", "Plato") == work_key("the republic", "PLATO")
    with pytest.raises(ValueError):
        resolve("   ", "x")


# --- storage and the full play ---------------------------------------------

def test_first_play_is_early_and_counters_update(client: TestClient):
    play = name_ten.submit_play(name_ten.FREE_PLAY, _items("Alpha"), anon_id="anon-1")
    assert play["score"] == 50
    assert play["findings_json"]["early"] is True
    assert play["max_overlap"] == 0
    db = get_db()
    assert db.execute("SELECT count(*) FROM ten_work_stat").fetchone()[0] == 10
    assert db.execute("SELECT count(*) FROM ten_pair_stat").fetchone()[0] == 45
    assert db.execute("SELECT max(list_count) FROM ten_pair_stat").fetchone()[0] == 1
    stored = store.get_play(play["id"])
    assert [item["position"] for item in stored["items"]] == list(range(1, 11))
    assert stored["findings_json"]["lists_before"] == 0


def test_repeating_a_list_finds_it_and_scores_lower(client: TestClient):
    first = name_ten.submit_play(name_ten.FREE_PLAY, _items("Beta"), anon_id="anon-1")
    name_ten.submit_play(name_ten.FREE_PLAY, _items("Gamma"), anon_id="anon-2")
    copy = name_ten.submit_play(name_ten.FREE_PLAY, list(reversed(_items("Beta"))), anon_id="anon-3")
    fresh = name_ten.submit_play(name_ten.FREE_PLAY, _items("Delta"), anon_id="anon-4")
    assert copy["max_overlap"] == 10
    assert copy["findings_json"]["closest_play"] == first["id"]
    assert copy["combo_hash"] == first["combo_hash"]
    assert fresh["raw_score"] > copy["raw_score"]
    assert fresh["score"] > copy["score"]


def test_one_ranked_play_per_daily_game_but_free_play_repeats(client: TestClient):
    from datetime import date

    _ = client.post("/auth/register", data={"email": "ten@example.com", "password": "a-good-password",
                                            "display_name": "Ten"}, follow_redirects=False)
    user_id = get_db().execute("SELECT id FROM users WHERE email = 'ten@example.com'").fetchone()[0]
    store.add_game(47, "Ten books for someone who just lost their faith", date(2026, 11, 2))
    name_ten.submit_play(47, _items("Eps"), user_id=user_id)
    with pytest.raises(store.AlreadyPlayed):
        name_ten.submit_play(47, _items("Zeta"), user_id=user_id)
    name_ten.submit_play(name_ten.FREE_PLAY, _items("Eta"), user_id=user_id)
    name_ten.submit_play(name_ten.FREE_PLAY, _items("Theta"), user_id=user_id)
    assert store.game_for(date(2026, 11, 2))["id"] == 47


def test_missing_eleventh_is_a_library_book_named_alongside_the_list(client: TestClient):
    reset_index()
    work = CatalogService().get_works()[0]
    library = resolve(work["title"], work["author"])
    base = _items("Kappa", 9)
    for n in range(3):
        name_ten.submit_play(name_ten.FREE_PLAY, base + [library], anon_id=f"anon-k{n}")
    newcomer = name_ten.submit_play(name_ten.FREE_PLAY, base + _items("Lambda", 1), anon_id="anon-new")
    eleventh = newcomer["findings_json"]["missing_eleventh"]
    assert eleventh and eleventh["work_key"] == library["work_key"]
    assert eleventh["book_id"] == library["book_id"]


def test_unknown_game_and_anonymous_without_id_are_refused(client: TestClient):
    with pytest.raises(ValueError):
        name_ten.submit_play(999, _items("Mu"), anon_id="a")
    with pytest.raises(ValueError):
        name_ten.submit_play(name_ten.FREE_PLAY, _items("Nu"))
