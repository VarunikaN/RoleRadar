from __future__ import annotations

import json
import sqlite3
from itertools import islice
from pathlib import Path
from typing import Any

from .sources import query_matches

LEVEL_GROUPS = {
    "junior": ("junior",),
    "mid": ("mid",),
    "senior": ("senior", "lead", "principal"),
}


def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class JobStore:
    def __init__(self, path: Path) -> None:
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                company_name TEXT NOT NULL,
                location TEXT,
                workplace TEXT,
                experience_level TEXT,
                description TEXT,
                requirements TEXT,
                tags TEXT NOT NULL,
                apply_url TEXT,
                created_at TEXT,
                fetched_at TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT ''
            )
            """
        )
        columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(jobs)")}
        if "source" not in columns:
            self.connection.execute("ALTER TABLE jobs ADD COLUMN source TEXT NOT NULL DEFAULT ''")
        self.connection.commit()

    def upsert_jobs(self, jobs: list[dict[str, Any]], fetched_at: str) -> int:
        rows = [
            (
                str(job.get("id", "")),
                job.get("title") or "Untitled role",
                job.get("company_name") or "Unknown company",
                job.get("location") or "",
                job.get("workplace") or "",
                job.get("experience_level") or "",
                job.get("description") or "",
                job.get("requirements") or "",
                json.dumps(job.get("tags") or []),
                job.get("apply_url") or "",
                job.get("created_at") or "",
                fetched_at,
                job.get("source") or "",
            )
            for job in jobs
            if job.get("id")
        ]
        self.connection.executemany(
            """
            INSERT INTO jobs (id, title, company_name, location, workplace, experience_level, description,
                requirements, tags, apply_url, created_at, fetched_at, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title, company_name=excluded.company_name,
                location=excluded.location, workplace=excluded.workplace,
                experience_level=excluded.experience_level,
                description=excluded.description, requirements=excluded.requirements,
                tags=excluded.tags, apply_url=excluded.apply_url,
                created_at=excluded.created_at, fetched_at=excluded.fetched_at, source=excluded.source
            """,
            rows,
        )
        self.connection.commit()
        return len(rows)

    def search(
        self,
        query: str = "",
        remote_only: bool = False,
        limit: int = 10,
        level: str | None = None,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM jobs WHERE 1=1"
        params: list[Any] = []
        for word in query.lower().split():
            term = _like(word)
            sql += (
                " AND (lower(title) LIKE ? ESCAPE '\\' OR lower(company_name) LIKE ? ESCAPE '\\'"
                " OR lower(description) LIKE ? ESCAPE '\\' OR lower(tags) LIKE ? ESCAPE '\\')"
            )
            params.extend([term] * 4)
        if remote_only:
            sql += " AND lower(workplace) = 'remote'"
        group = LEVEL_GROUPS.get(level or "")
        if group:
            sql += f" AND lower(experience_level) IN ({', '.join('?' for _ in group)})"
            params.extend(group)
        sql += " ORDER BY created_at DESC"
        jobs = (self._job(dict(row)) for row in self.connection.execute(sql, params))
        matching = (job for job in jobs if query_matches(job, query))
        return list(islice(matching, limit))

    def all_jobs(self) -> list[dict[str, Any]]:
        return [self._job(dict(row)) for row in self.connection.execute("SELECT * FROM jobs")]

    def count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0])

    @staticmethod
    def _job(job: dict[str, Any]) -> dict[str, Any]:
        try:
            tags = json.loads(job["tags"])
        except (TypeError, ValueError):
            tags = []
        job["tags"] = tags if isinstance(tags, list) else []
        return job
