"""Facts about a list that the verdict screen and the judge may state. Pure functions."""

from __future__ import annotations

from typing import Callable

from .scoring import expected_together, pair_surprise

MIN_BOOK_LISTS = 5       # a pair needs both books seen this often to be called "rare"
MIN_ELEVENTH_PAIRS = 3   # a candidate must co-occur this often with a book on the list


def rarest_pair(items: list[dict], n_lists: int, work_counts: dict, priors: dict, pair_counts: dict) -> dict | None:
    by_key = {item["work_key"]: item for item in items}
    best = None
    keys = sorted(by_key)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if work_counts.get(a, 0) < MIN_BOOK_LISTS or work_counts.get(b, 0) < MIN_BOOK_LISTS:
                continue
            surprise = pair_surprise(a, b, n_lists, work_counts, priors, pair_counts)
            if best is None or surprise > best[0]:
                best = (surprise, a, b)
    if not best:
        return None
    _, a, b = best
    together = pair_counts.get((a, b), 0)
    expected = expected_together(a, b, n_lists, work_counts, priors)
    return {
        "titles": [by_key[a]["title"], by_key[b]["title"]],
        "together": together,
        "never_seen": together == 0 and expected >= 1,
    }


def most_common(items: list[dict], n_lists: int, work_counts: dict) -> dict | None:
    if n_lists <= 0:
        return None
    named = [(work_counts.get(item["work_key"], 0), item) for item in items]
    count, item = max(named, key=lambda pair: pair[0])
    if count <= 0:
        return None
    return {"title": item["title"], "lists": count, "one_in": max(1, round(n_lists / count))}


def missing_eleventh(items: list[dict], n_lists: int, work_counts: dict, priors: dict,
                     co_named: list[tuple[str, str, int]], library_book: Callable[[str], dict | None]) -> dict | None:
    """The library book most strongly named alongside this list, and not on it."""
    on_list = {item["work_key"] for item in items}
    affinity: dict[str, float] = {}
    volume: dict[str, int] = {}
    for a, b, count in co_named:
        if (a in on_list) == (b in on_list):
            continue
        inside, outside = (a, b) if a in on_list else (b, a)
        volume[outside] = volume.get(outside, 0) + count
        if count < MIN_ELEVENTH_PAIRS:
            continue
        pair = tuple(sorted((inside, outside)))
        affinity[outside] = affinity.get(outside, 0.0) - pair_surprise(
            inside, outside, n_lists, work_counts, priors, {pair: count}
        )
    ranked = sorted(affinity, key=lambda key: affinity[key], reverse=True) or \
        sorted(volume, key=lambda key: volume[key], reverse=True)
    for key in ranked:
        book = library_book(key)
        if book and book.get("readable", True):
            return {"work_key": key, "title": book["title"], "author": book["author"], "book_id": book["book_id"]}
    return None


def compute(items: list[dict], *, n_lists: int, work_counts: dict, priors: dict, pair_counts: dict,
            max_overlap: int, co_named: list[tuple[str, str, int]],
            library_book: Callable[[str], dict | None]) -> dict:
    return {
        "lists_before": n_lists,
        "rarest_pair": rarest_pair(items, n_lists, work_counts, priors, pair_counts),
        "most_common": most_common(items, n_lists, work_counts),
        "closest_shared": max_overlap,
        "missing_eleventh": missing_eleventh(items, n_lists, work_counts, priors, co_named, library_book),
        "unverified": sum(1 for item in items if item["status"] == "unverified"),
        "in_library": sum(1 for item in items if item["status"] == "library"),
    }
