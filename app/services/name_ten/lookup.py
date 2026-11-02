"""Book search for the Name Ten slots: the library first, then Open Library.

Open Library is called from the server (the page's CSP only allows our own
origin) with a short timeout and an in-memory cache. Every Open Library book
we hand to a player is remembered with its popularity, so a submitted pick can
be marked as a real book (`finder`) without a second lookup.
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

from ..catalog_normalization import clean_catalog_text, normalized_identity
from .identity import _library_index, author_key, title_key, work_key

logger = logging.getLogger(__name__)

OPEN_LIBRARY_URL = "https://openlibrary.org/search.json"
OPEN_LIBRARY_TIMEOUT = 2.5
SEARCH_TTL = 24 * 3600
MAX_CACHE = 4000
MAX_RESULTS = 6

_search_cache: dict[str, tuple[float, list[dict]]] = {}
_seen: dict[str, dict] = {}            # work_key -> {"title","author","popularity"} served from Open Library
_slots = asyncio.Semaphore(4)


def reset() -> None:
    _search_cache.clear()
    _seen.clear()


def search_library(query: str, limit: int = MAX_RESULTS) -> list[dict]:
    """Works whose title and author contain every word of the query; title-prefix matches first."""
    words = normalized_identity(query).split()
    if not words:
        return []
    phrase = " ".join(words)
    ranked = []
    for key, work in _library_index().items():
        title = normalized_identity(work["title"])
        haystack = f"{title} {normalized_identity(work['author'])}"
        if not all(word in haystack for word in words):
            continue
        rank = 0 if title.startswith(phrase) else 1 if phrase in title else 2
        ranked.append((rank, len(title), work["title"], key, work))
    ranked.sort(key=lambda row: row[:3])
    return [{"work_key": key, "title": work["title"], "author": work["author"], "source": "library",
             "book_id": work["book_id"]} for *_, key, work in ranked[:limit]]


async def _fetch_open_library(query: str) -> list[dict]:
    params = {"q": query, "limit": 10, "fields": "key,title,author_name,readinglog_count"}
    async with _slots:
        async with httpx.AsyncClient(timeout=OPEN_LIBRARY_TIMEOUT, headers={"User-Agent": "LibXNDR (libxndr.com)"}) as client:
            response = await client.get(OPEN_LIBRARY_URL, params=params)
            response.raise_for_status()
            return response.json().get("docs", [])


def _remember(key: str, value) -> None:
    if len(_search_cache) >= MAX_CACHE:
        _search_cache.pop(next(iter(_search_cache)))
    _search_cache[key] = (time.monotonic(), value)


async def search_open_library(query: str) -> list[dict]:
    query = clean_catalog_text(query)[:120]
    cache_key = normalized_identity(query)
    if len(cache_key) < 3:
        return []
    cached = _search_cache.get(cache_key)
    if cached and time.monotonic() - cached[0] < SEARCH_TTL:
        return cached[1]
    try:
        docs = await _fetch_open_library(query)
    except Exception as exc:
        logger.info("Open Library search failed (%s)", type(exc).__name__)
        return []
    results, keys = [], set()
    for doc in docs:
        title = clean_catalog_text(doc.get("title", ""))[:300]
        author = clean_catalog_text((doc.get("author_name") or [""])[0])[:200]
        if not title:
            continue
        key = work_key(title, author)
        if key in keys:
            continue
        keys.add(key)
        popularity = doc.get("readinglog_count")
        popularity = float(popularity) if isinstance(popularity, (int, float)) else None
        if len(_seen) >= MAX_CACHE * 5:
            _seen.pop(next(iter(_seen)))
        _seen[key] = {"title": title, "author": author, "popularity": popularity}
        results.append({"work_key": key, "title": title, "author": author, "source": "openlibrary",
                        "popularity": popularity})
    # Most-read first: a typed "republic" should offer Plato before a 1987 thesis.
    results.sort(key=lambda row: -(row["popularity"] or 0))
    _remember(cache_key, results)
    return results


async def search(query: str, limit: int = MAX_RESULTS) -> list[dict]:
    library = search_library(query, limit)
    if len(library) >= limit:
        return library
    taken = {row["work_key"] for row in library}
    outside = [row for row in await search_open_library(query) if row["work_key"] not in taken]
    return library + [{key: row[key] for key in ("work_key", "title", "author", "source")}
                      for row in outside][: limit - len(library)]


def seen(key: str) -> dict | None:
    return _seen.get(key)


async def confirm(title: str, author: str) -> dict | None:
    """Ask Open Library whether a typed book exists. Returns the book as Open
    Library has it (with work_key and popularity), or None."""
    key = work_key(title, author)
    if key not in _seen:
        results = await search_open_library(f"{title} {author}".strip())
        if key not in _seen and not author_key(author):
            # Typed without an author: take the most-read book with that exact title.
            wanted = title_key(title)
            match = next((row for row in results if title_key(row["title"]) == wanted), None)
            if match:
                return {**_seen[match["work_key"]], "work_key": match["work_key"]}
    found = _seen.get(key)
    return {**found, "work_key": key} if found else None
