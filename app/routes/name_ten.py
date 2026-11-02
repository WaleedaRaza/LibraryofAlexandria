"""Name Ten: the play screen, book search for its slots, and play submission.

Anyone can play. Before signing in a player is a random id the page keeps in
localStorage (Firebase Hosting forwards only the session cookie, so a second
cookie would never reach us); signing in claims those plays for the account.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from .. import templates
from ..config import settings
from ..services import name_ten
from ..services.name_ten import lookup, store
from .auth import get_current_user_optional

router = APIRouter()
logger = logging.getLogger(__name__)

ANON_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
PLAY_LIMIT = (30, 3600)       # plays per player per hour
SEARCH_LIMIT = (120, 60)      # searches per visitor per minute
_times: dict[str, list[float]] = defaultdict(list)


def _require_enabled() -> None:
    if not settings.NAME_TEN_ENABLED:
        raise HTTPException(status_code=404, detail="Not found")


def _allow(bucket: str, limit: tuple[int, int]) -> bool:
    count, window = limit
    now = time.monotonic()
    recent = [moment for moment in _times[bucket] if now - moment < window]
    if len(recent) >= count:
        _times[bucket] = recent
        return False
    recent.append(now)
    _times[bucket] = recent
    return True


def _visitor(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def _today() -> date:
    """Daily games turn over at midnight in New York."""
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:
        return (datetime.now(timezone.utc) - timedelta(hours=5)).date()


def _anon(value) -> str | None:
    value = str(value or "").strip().lower()
    return value if ANON_ID.match(value) else None


@router.get("", response_class=HTMLResponse)
async def play_page(request: Request, user=Depends(get_current_user_optional)):
    _require_enabled()
    daily = store.game_for(_today())
    already = store.played(daily["id"], user["id"]) if daily and user else None
    return templates.TemplateResponse("ten/play.html", {
        "request": request,
        "user": user,
        "daily": daily,
        "daily_done": bool(already),
        "free_play": name_ten.FREE_PLAY,
    })


@router.get("/search", response_class=JSONResponse)
async def search_books(request: Request, q: str = ""):
    _require_enabled()
    query = q.strip()[:120]
    if len(query) < 2:
        return {"results": []}
    if not _allow(f"search:{_visitor(request)}", SEARCH_LIMIT):
        raise HTTPException(status_code=429, detail="Slow down a little.")
    return {"results": await lookup.search(query)}


async def _resolve_items(raw_items) -> list[dict]:
    if not isinstance(raw_items, list) or len(raw_items) != 10:
        raise ValueError("Name ten books.")
    picks = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise ValueError("Every slot needs a title.")
        picks.append(name_ten.resolve(str(raw.get("title", ""))[:300], str(raw.get("author", ""))[:200]))
    # Books not in the library: confirm them with Open Library, all at once, briefly.
    outside = [index for index, item in enumerate(picks) if item["status"] != "library"]
    answers = await asyncio.gather(*(lookup.confirm(picks[i]["title"], picks[i]["author"]) for i in outside),
                                   return_exceptions=True)
    popularity = []
    for index, found in zip(outside, answers):
        if not isinstance(found, dict):
            continue
        item = picks[index]
        if not item["author"]:
            item.update(work_key=found["work_key"], title=found["title"], author=found["author"])
        item["status"] = "finder"
        popularity.append({"work_key": item["work_key"], "title": item["title"], "author": item["author"],
                           "prior_popularity": found.get("popularity")})
    store.set_popularity(popularity)
    return picks


def _public_result(play: dict) -> dict:
    facts = play["findings_json"]
    return {
        "play_id": play["id"],
        "score": play["score"],
        "early": facts.get("early", False),
        "ranked_against": facts.get("ranked_against", 0),
        "lists_before": facts.get("lists_before", 0),
        "closest_shared": play["max_overlap"],
        "rarest_pair": facts.get("rarest_pair"),
        "most_common": facts.get("most_common"),
        "missing_eleventh": facts.get("missing_eleventh"),
        "items": [{key: item.get(key) for key in ("position", "title", "author", "status", "book_id")}
                  for item in play["items"]],
    }


@router.post("/play", response_class=JSONResponse)
async def submit(request: Request, user=Depends(get_current_user_optional)):
    _require_enabled()
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Send the list as JSON.")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Send the list as JSON.")
    anon_id = None if user else _anon(payload.get("anon_id"))
    if not user and not anon_id:
        raise HTTPException(status_code=400, detail="Reload the page and try again.")
    if not _allow(f"play:{user['id'] if user else anon_id}", PLAY_LIMIT) or \
            not _allow(f"play-ip:{_visitor(request)}", (PLAY_LIMIT[0] * 3, PLAY_LIMIT[1])):
        raise HTTPException(status_code=429, detail="That is a lot of lists for one hour. Come back in a bit.")
    try:
        game_id = int(payload.get("game_id", name_ten.FREE_PLAY))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Unknown game.")
    if game_id != name_ten.FREE_PLAY:
        today = store.game_for(_today())
        if not today or today["id"] != game_id:
            raise HTTPException(status_code=409, detail="That daily game has closed. Today's is open.")
    try:
        items = await _resolve_items(payload.get("items"))
        play = await asyncio.to_thread(
            name_ten.submit_play, game_id, items, user_id=user["id"] if user else None, anon_id=anon_id
        )
    except store.AlreadyPlayed as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _public_result(play)


@router.post("/claim", response_class=JSONResponse)
async def claim(request: Request, user=Depends(get_current_user_optional)):
    """After signing in, the page hands over its anonymous id once."""
    _require_enabled()
    if not user:
        raise HTTPException(status_code=401, detail="Sign in first.")
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    anon_id = _anon(payload.get("anon_id") if isinstance(payload, dict) else None)
    if not anon_id:
        return {"claimed": 0}
    return {"claimed": store.claim_anonymous(anon_id, user["id"])}
