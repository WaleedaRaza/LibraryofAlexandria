"""Name Ten: name ten books, get a combo uniqueness score and the facts behind it.

Entry point: `submit_play`. The routes, judge and share cards build on it in
later releases; this package has no web or model dependencies of its own.
"""

from __future__ import annotations

import uuid

from . import findings, scoring, store
from .identity import library_book, resolve, work_key

__all__ = ["submit_play", "resolve", "work_key", "FREE_PLAY"]

FREE_PLAY = 0


def submit_play(game_id: int, items: list[dict], *, user_id: str | None = None,
                anon_id: str | None = None) -> dict:
    """Score a list of ten resolved items (see identity.resolve), store it and return the result.

    The score is frozen at submission, ranked against earlier plays only.
    """
    if not user_id and not anon_id:
        raise ValueError("A play needs a player.")
    if not store.get_game(game_id):
        raise ValueError("That game does not exist.")
    keys = scoring.ordered_keys([item["work_key"] for item in items])
    items = [{**item, "position": index} for index, item in enumerate(items, start=1)]

    n_lists = store.list_count()
    work_counts, popularity = store.work_stats(keys)
    priors = {key: scoring.prior(popularity.get(key)) for key in keys}
    pairs = store.pair_counts(keys)
    closest_play, max_overlap = store.closest_overlap(keys)
    raw = scoring.combo_raw(keys, n_lists, work_counts, priors, pairs, max_overlap)

    co_named = store.co_named(keys)
    outside = sorted({key for pair in co_named for key in pair[:2]} - set(keys))
    outside_counts, outside_popularity = store.work_stats(outside)
    all_counts = {**work_counts, **outside_counts}
    all_priors = {**priors, **{key: scoring.prior(outside_popularity.get(key)) for key in outside}}
    facts = findings.compute(
        items, n_lists=n_lists, work_counts=all_counts, priors=all_priors, pair_counts=pairs,
        max_overlap=max_overlap, co_named=co_named, library_book=library_book,
    )

    early = store.plays_in_game(game_id) < scoring.EARLY_GAME
    below, equal, total = store.rank_counts(raw, None if early else game_id)
    score = scoring.percentile_score(below, equal, total)
    facts.update({"early": early, "ranked_against": total, "closest_play": closest_play})

    play = {
        "id": f"play_{uuid.uuid4().hex}",
        "game_id": game_id,
        "user_id": user_id,
        "anon_id": None if user_id else anon_id,
        "combo_hash": scoring.combo_hash(keys),
        "raw_score": raw,
        "score": score,
        "max_overlap": max_overlap,
        "findings_json": facts,
        "badges_json": [],
    }
    store.save_play(play, items)
    return {**play, "items": items}
