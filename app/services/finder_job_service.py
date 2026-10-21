"""Durable, reader-owned source-finder jobs driven one title at a time."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone

from ..db.database import get_db, get_supabase, is_sqlite_mode
from .reading_desk import find_readings

_finder_slots = asyncio.Semaphore(2)


def _decode_item(row: dict) -> dict:
    item = dict(row)
    if isinstance(item.get("candidates_json"), str):
        item["candidates_json"] = json.loads(item["candidates_json"])
    item["candidates"] = item.pop("candidates_json", [])
    return item


def _public_candidates(results: list[dict]) -> list[dict]:
    candidates = []
    for row in results:
        url = row.get("final_url") or row.get("url")
        if not row.get("viewable") or not str(url).startswith(("https://", "http://")):
            continue
        candidates.append({
            "title": row.get("title") or row.get("domain") or "Book candidate",
            "url": url,
            "domain": row.get("domain"),
            "page_count": row.get("page_count"),
            "score": row.get("score"),
            "edition_fit": row.get("edition_fit"),
            "reasons": (row.get("reasons") or [])[:8],
        })
    return candidates[:10]


class FinderJobService:
    def list_for_user(self, user_id: str, limit: int = 12) -> list[dict]:
        limit = max(1, min(limit, 50))
        if is_sqlite_mode():
            rows = get_db().execute(
                "SELECT * FROM source_jobs WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        else:
            rows = get_supabase().table("source_jobs").select("*").eq(
                "user_id", user_id
            ).order("created_at", desc=True).limit(limit).execute().data or []
        jobs = []
        for row in rows:
            job = dict(row)
            job["percent"] = round(job.get("completed", 0) / max(job.get("total", 1), 1) * 100)
            jobs.append(job)
        return jobs

    def create(self, user_id: str, books: list[dict[str, str]]) -> str:
        if is_sqlite_mode():
            active = get_db().execute("SELECT count(*) FROM source_jobs WHERE user_id=? AND status IN ('queued','running')", (user_id,)).fetchone()[0]
            recent = get_db().execute("SELECT coalesce(sum(total),0) FROM source_jobs WHERE user_id=? AND created_at >= datetime('now','-1 day')", (user_id,)).fetchone()[0]
        else:
            database = get_supabase()
            active = len(database.table("source_jobs").select("id").eq("user_id", user_id).in_("status", ["queued", "running"]).execute().data or [])
            since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
            recent = sum(row["total"] for row in (database.table("source_jobs").select("total").eq("user_id", user_id).gte("created_at", since).execute().data or []))
        if active >= 2:
            raise ValueError("Finish or stop an active source run before starting another.")
        if recent + len(books) > 100:
            raise ValueError("The daily finder limit is 100 titles per account. Resume tomorrow.")
        job_id = f"find_{uuid.uuid4().hex}"
        job = {"id": job_id, "user_id": user_id, "total": len(books), "status": "queued"}
        items = [{"id": f"finditem_{uuid.uuid4().hex}", "job_id": job_id, "position": index,
                  "title": book["title"], "author": book["author"], "status": "queued"}
                 for index, book in enumerate(books)]
        if is_sqlite_mode():
            db = get_db()
            with db:
                db.execute("INSERT INTO source_jobs(id,user_id,total,status) VALUES(:id,:user_id,:total,:status)", job)
                db.executemany("INSERT INTO source_job_items(id,job_id,position,title,author,status) VALUES(:id,:job_id,:position,:title,:author,:status)", items)
        else:
            database = get_supabase()
            try:
                database.table("source_jobs").insert(job).execute()
                database.table("source_job_items").insert(items).execute()
            except Exception:
                database.table("source_jobs").delete().eq("id", job_id).eq("user_id", user_id).execute()
                raise
        return job_id

    def get(self, job_id: str, user_id: str) -> dict | None:
        if is_sqlite_mode():
            row = get_db().execute("SELECT * FROM source_jobs WHERE id=? AND user_id=?", (job_id, user_id)).fetchone()
            items = get_db().execute("SELECT * FROM source_job_items WHERE job_id=? ORDER BY position", (job_id,)).fetchall() if row else []
        else:
            rows = get_supabase().table("source_jobs").select("*").eq("id", job_id).eq("user_id", user_id).limit(1).execute().data or []
            row = rows[0] if rows else None
            items = get_supabase().table("source_job_items").select("*").eq("job_id", job_id).order("position").execute().data or [] if row else []
        if not row:
            return None
        job = dict(row)
        job["items"] = [_decode_item(item) for item in items]
        return job

    async def work_next(self, job_id: str, user_id: str) -> dict | None:
        job = self.get(job_id, user_id)
        if not job or job["status"] in {"complete", "cancelled"}:
            return job
        item = next((row for row in job["items"] if row["status"] in {"queued", "running"}), None)
        if not item:
            self._update_job(job_id, user_id, status="complete", completed=job["total"])
            return self.get(job_id, user_id)
        self._update_item(item["id"], status="running")
        self._update_job(job_id, user_id, status="running", completed=job["completed"])
        try:
            async with _finder_slots:
                results = await asyncio.wait_for(find_readings(item["title"], item["author"]), timeout=50)
            self._update_item(item["id"], status="complete", candidates=_public_candidates(results), error=None)
        except Exception as exc:
            self._update_item(item["id"], status="failed", candidates=[], error=f"{type(exc).__name__}: search did not complete"[:180])
        refreshed = self.get(job_id, user_id)
        if refreshed["status"] == "cancelled":
            return refreshed
        completed = sum(row["status"] in {"complete", "failed", "cancelled"} for row in refreshed["items"])
        status = "complete" if completed >= refreshed["total"] else "running"
        self._update_job(job_id, user_id, status=status, completed=completed)
        return self.get(job_id, user_id)

    def cancel(self, job_id: str, user_id: str) -> bool:
        job = self.get(job_id, user_id)
        if not job or job["status"] in {"complete", "cancelled"}:
            return False
        if is_sqlite_mode():
            db = get_db()
            with db:
                db.execute("UPDATE source_jobs SET status='cancelled',updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?", (job_id, user_id))
                db.execute("UPDATE source_job_items SET status='cancelled',updated_at=CURRENT_TIMESTAMP WHERE job_id=? AND status='queued'", (job_id,))
        else:
            get_supabase().table("source_jobs").update({"status": "cancelled"}).eq("id", job_id).eq("user_id", user_id).execute()
            get_supabase().table("source_job_items").update({"status": "cancelled"}).eq("job_id", job_id).eq("status", "queued").execute()
        return True

    def candidate_urls(self, job_id: str, item_id: str, user_id: str, selected: list[str]) -> tuple[dict, list[str]]:
        job = self.get(job_id, user_id)
        item = next((row for row in job["items"] if row["id"] == item_id), None) if job else None
        if not item:
            raise ValueError("Finder result not found.")
        allowed = {row["url"] for row in item["candidates"]}
        if any(url not in allowed for url in selected):
            raise ValueError("One selected result does not belong to this source run.")
        urls = list(dict.fromkeys(url for url in selected if url in allowed))
        if not urls:
            raise ValueError("Select at least one result to save.")
        return item, urls

    def _update_item(self, item_id: str, *, status: str, candidates: list[dict] | None = None, error: str | None = None) -> None:
        record = {"status": status, "error": error}
        if candidates is not None:
            record["candidates_json"] = candidates
        if is_sqlite_mode():
            get_db().execute("UPDATE source_job_items SET status=?,candidates_json=coalesce(?,candidates_json),error=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                             (status, json.dumps(candidates) if candidates is not None else None, error, item_id))
            get_db().commit()
        else:
            get_supabase().table("source_job_items").update(record).eq("id", item_id).execute()

    def _update_job(self, job_id: str, user_id: str, *, status: str, completed: int) -> None:
        if is_sqlite_mode():
            get_db().execute("UPDATE source_jobs SET status=?,completed=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?",
                             (status, completed, job_id, user_id))
            get_db().commit()
        else:
            get_supabase().table("source_jobs").update({"status": status, "completed": completed}).eq("id", job_id).eq("user_id", user_id).execute()
