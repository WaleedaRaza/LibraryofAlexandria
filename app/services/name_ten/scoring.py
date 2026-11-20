"""Combo uniqueness: how much less often these books are named together than chance predicts.

For each pair of books, compare how many lists named them together with how
many would have if each book were picked independently at its own popularity
(a smoothed log ratio, close to pointwise mutual information). A pair that
should have shown up together many times but never has is surprising. A pair
nobody could have been expected to name together (obscure or made-up books)
scores about zero, so obscurity alone earns nothing. Copying an earlier list
is penalised through the overlap term. Pure functions only; the database lives
in store.py.
"""

from __future__ import annotations

import hashlib
from math import log10, log2

ALPHA = 50.0          # pseudo-lists behind each book's prior popularity
PAIR_SMOOTHING = 1.0  # pseudo-count on both sides of the expected/observed ratio
LAMBDA = 1.5          # bits per book not shared with the closest earlier list
DEFAULT_PRIOR = 0.01  # chance a list names a book we know nothing about
LIST_SIZE = 10
PAIRS = LIST_SIZE * (LIST_SIZE - 1) // 2
EARLY_GAME = 200      # below this many plays, rank against all plays ever


def prior(popularity: float | None) -> float:
    """Open Library reading-log count → prior chance a list names the book."""
    if popularity is None:
        return DEFAULT_PRIOR
    return min(0.05, max(0.0005, log10(1 + max(0.0, popularity)) / 100))


def ordered_keys(keys: list[str]) -> list[str]:
    unique = sorted(set(keys))
    if len(unique) != LIST_SIZE or len(keys) != LIST_SIZE:
        raise ValueError("Name ten different books.")
    return unique


def combo_hash(keys: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(keys)).encode()).hexdigest()


def book_rate(key: str, n_lists: int, work_counts: dict, priors: dict) -> float:
    return (work_counts.get(key, 0) + ALPHA * priors.get(key, DEFAULT_PRIOR)) / (n_lists + ALPHA)


def expected_together(a: str, b: str, n_lists: int, work_counts: dict, priors: dict) -> float:
    return n_lists * book_rate(a, n_lists, work_counts, priors) * book_rate(b, n_lists, work_counts, priors)


def pair_surprise(a: str, b: str, n_lists: int, work_counts: dict, priors: dict, pair_counts: dict) -> float:
    """Bits by which a and b are named together less often than chance; about 0 with no evidence."""
    a, b = sorted((a, b))
    expected = expected_together(a, b, n_lists, work_counts, priors)
    observed = pair_counts.get((a, b), 0)
    return log2((expected + PAIR_SMOOTHING) / (observed + PAIR_SMOOTHING))


def combo_raw(keys: list[str], n_lists: int, work_counts: dict, priors: dict,
              pair_counts: dict, max_overlap: int) -> float:
    keys = ordered_keys(keys)
    total = 0.0
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            total += pair_surprise(a, b, n_lists, work_counts, priors, pair_counts)
    return total / PAIRS + LAMBDA * (LIST_SIZE - max_overlap)


def percentile_score(below: int, equal: int, total: int) -> int:
    """0–100: share of comparable earlier plays this one beats (ties count half)."""
    if total <= 0:
        return 50
    return max(0, min(100, round(100 * (below + 0.5 * equal) / total)))
