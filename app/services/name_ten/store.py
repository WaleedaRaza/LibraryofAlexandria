"""Name Ten persistence, in SQLite (local and tests) and Supabase (production)."""

from __future__ import annotations

import json
import sqlite3
from datetime import date

from ...db.database import get_db, get_supabase, is_sqlite_mode


class AlreadyPlayed(ValueError):
    pass


def _placeholders(values: list) -> str:
    return ",".join("?" for _ in values)


def game_for(day: date) -> dict | None:
    if is_sqlite_mode():
        row = get_db().execute("SELECT * FROM ten_game WHERE opens_on = ?", (day.isoformat(),)).fetchone()
        return dict(row) if row else None
    rows = get_supabase().table("ten_game").select("*").eq("opens_on", day.isoformat()).limit(1).execute().data
    return rows[0] if rows else None


def get_game(game_id: int) -> dict | None:
    if is_sqlite_mode():
        row = get_db().execute("SELECT * FROM ten_game WHERE id = ?", (game_id,)).fetchone()
        return dict(row) if row else None
    rows = get_supabase().table("ten_game").select("*").eq("id", game_id).limit(1).execute().data
    return rows[0] if rows else None


def add_game(game_id: int, prompt: str, opens_on: date) -> None:
    record = {"id": game_id, "kind": "daily", "prompt": prompt, "opens_on": opens_on.isoformat()}
    if is_sqlite_mode():
        db = get_db()
        db.execute("INSERT INTO ten_game(id,kind,prompt,opens_on) VALUES(:id,:kind,:prompt,:opens_on)", record)
        db.commit()
    else:
        get_supabase().table("ten_game").insert(record).execute()


def list_count() -> int:
    if is_sqlite_mode():
        return get_db().execute("SELECT count(*) FROM ten_play").fetchone()[0]
    return get_supabase().table("ten_play").select("id", count="exact").limit(1).execute().count or 0


def work_stats(keys: list[str]) -> tuple[dict[str, int], dict[str, float | None]]:
    if not keys:
        return {}, {}
    if is_sqlite_mode():
        rows = [dict(row) for row in get_db().execute(
            f"SELECT work_key,list_count,prior_popularity FROM ten_work_stat WHERE work_key IN ({_placeholders(keys)})",
            keys,
        )]
    else:
        rows = get_supabase().table("ten_work_stat").select("work_key,list_count,prior_popularity").in_(
            "work_key", keys
        ).execute().data or []
    return ({row["work_key"]: row["list_count"] for row in rows},
            {row["work_key"]: row["prior_popularity"] for row in rows})


def pair_counts(keys: list[str]) -> dict[tuple[str, str], int]:
    if is_sqlite_mode():
        rows = get_db().execute(
            f"SELECT work_a,work_b,list_count FROM ten_pair_stat "
            f"WHERE work_a IN ({_placeholders(keys)}) AND work_b IN ({_placeholders(keys)})",
            keys + keys,
        ).fetchall()
        rows = [dict(row) for row in rows]
    else:
        rows = get_supabase().rpc("ten_pair_counts", {"keys": keys}).execute().data or []
    return {(row["work_a"], row["work_b"]): row["list_count"] for row in rows}


def co_named(keys: list[str], limit: int = 400) -> list[tuple[str, str, int]]:
    if is_sqlite_mode():
        marks = _placeholders(keys)
        rows = get_db().execute(
            f"SELECT work_a,work_b,list_count FROM ten_pair_stat "
            f"WHERE (work_a IN ({marks})) <> (work_b IN ({marks})) ORDER BY list_count DESC LIMIT ?",
            keys + keys + [limit],
        ).fetchall()
        rows = [dict(row) for row in rows]
    else:
        rows = get_supabase().rpc("ten_co_named", {"keys": keys, "lim": limit}).execute().data or []
    return [(row["work_a"], row["work_b"], row["list_count"]) for row in rows]


def closest_overlap(keys: list[str]) -> tuple[str | None, int]:
    if is_sqlite_mode():
        row = get_db().execute(
            f"SELECT play_id, count(*) shared FROM ten_play_item WHERE work_key IN ({_placeholders(keys)}) "
            "GROUP BY play_id ORDER BY shared DESC, play_id LIMIT 1",
            keys,
        ).fetchone()
        return (row["play_id"], row["shared"]) if row else (None, 0)
    rows = get_supabase().rpc("ten_closest_play", {"keys": keys}).execute().data or []
    return (rows[0]["play_id"], rows[0]["shared"]) if rows else (None, 0)


def plays_in_game(game_id: int) -> int:
    if is_sqlite_mode():
        return get_db().execute("SELECT count(*) FROM ten_play WHERE game_id = ?", (game_id,)).fetchone()[0]
    return get_supabase().table("ten_play").select("id", count="exact").eq("game_id", game_id).limit(1).execute().count or 0


def rank_counts(raw: float, game_id: int | None) -> tuple[int, int, int]:
    """(below, equal, total) among earlier plays of one game, or all plays when game_id is None."""
    if is_sqlite_mode():
        where, params = ("WHERE game_id = ?", [game_id]) if game_id is not None else ("", [])
        row = get_db().execute(
            f"SELECT count(*) total, sum(raw_score < ?) below, sum(raw_score = ?) equal FROM ten_play {where}",
            [raw, raw] + params,
        ).fetchone()
        return row["below"] or 0, row["equal"] or 0, row["total"] or 0

    def count(op: str | None) -> int:
        query = get_supabase().table("ten_play").select("id", count="exact")
        if game_id is not None:
            query = query.eq("game_id", game_id)
        if op == "lt":
            query = query.lt("raw_score", raw)
        elif op == "eq":
            query = query.eq("raw_score", raw)
        return query.limit(1).execute().count or 0

    return count("lt"), count("eq"), count(None)


def save_play(play: dict, items: list[dict]) -> None:
    """Insert the play and its items, then bump the counters it contributes."""
    record = {**play, "findings_json": play["findings_json"], "badges_json": play.get("badges_json", [])}
    keys = [item["work_key"] for item in items]
    if is_sqlite_mode():
        db = get_db()
        try:
            with db:
                db.execute(
                    "INSERT INTO ten_play(id,game_id,user_id,anon_id,combo_hash,raw_score,score,max_overlap,"
                    "findings_json,badges_json) VALUES(:id,:game_id,:user_id,:anon_id,:combo_hash,:raw_score,"
                    ":score,:max_overlap,:findings_json,:badges_json)",
                    {**record, "findings_json": json.dumps(record["findings_json"]),
                     "badges_json": json.dumps(record["badges_json"])},
                )
                db.executemany(
                    "INSERT INTO ten_play_item(play_id,position,work_key,title,author,book_id,status) "
                    "VALUES(:play_id,:position,:work_key,:title,:author,:book_id,:status)",
                    [{**item, "play_id": play["id"]} for item in items],
                )
                db.executemany(
                    "INSERT INTO ten_work_stat(work_key,title,author,list_count) VALUES(?,?,?,1) "
                    "ON CONFLICT(work_key) DO UPDATE SET list_count = list_count + 1",
                    [(item["work_key"], item["title"], item["author"]) for item in items],
                )
                ordered = sorted(keys)
                db.executemany(
                    "INSERT INTO ten_pair_stat(work_a,work_b,list_count) VALUES(?,?,1) "
                    "ON CONFLICT(work_a,work_b) DO UPDATE SET list_count = list_count + 1",
                    [(a, b) for i, a in enumerate(ordered) for b in ordered[i + 1:]],
                )
        except sqlite3.IntegrityError as exc:
            if "ten_play.game_id, ten_play.user_id" in str(exc) or "idx_ten_one_daily_play" in str(exc):
                raise AlreadyPlayed("You already named your ten for today's game.") from exc
            raise
        return
    database = get_supabase()
    try:
        database.table("ten_play").insert(record).execute()
    except Exception as exc:
        if "idx_ten_one_daily_play" in str(exc) or "duplicate key" in str(exc):
            raise AlreadyPlayed("You already named your ten for today's game.") from exc
        raise
    try:
        database.table("ten_play_item").insert([{**item, "play_id": play["id"]} for item in items]).execute()
    except Exception:
        database.table("ten_play").delete().eq("id", play["id"]).execute()
        raise
    database.rpc("ten_record_list", {
        "keys": keys,
        "titles": [item["title"] for item in items],
        "authors": [item["author"] for item in items],
    }).execute()


def get_play(play_id: str) -> dict | None:
    if is_sqlite_mode():
        row = get_db().execute("SELECT * FROM ten_play WHERE id = ?", (play_id,)).fetchone()
        if not row:
            return None
        play = dict(row)
        for field in ("findings_json", "verdict_json", "badges_json"):
            if isinstance(play.get(field), str):
                play[field] = json.loads(play[field])
        items = [dict(item) for item in get_db().execute(
            "SELECT * FROM ten_play_item WHERE play_id = ? ORDER BY position", (play_id,)
        )]
    else:
        rows = get_supabase().table("ten_play").select("*").eq("id", play_id).limit(1).execute().data
        if not rows:
            return None
        play = rows[0]
        items = get_supabase().table("ten_play_item").select("*").eq("play_id", play_id).order(
            "position"
        ).execute().data or []
    play["items"] = items
    return play
