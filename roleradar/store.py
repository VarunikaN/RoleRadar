from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


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
                fetched_at TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def upsert_jobs(self, jobs: list[dict[str, Any]], fetched_at: str) -> int:
        rows = [
            (
                str(job.get("id", "")),
                job.get("title", "Untitled role"),
                job.get("company_name", "Unknown company"),
                job.get("location", ""),
                job.get("workplace", ""),
                job.get("experience_level", ""),
                job.get("description", ""),
                job.get("requirements", ""),
                json.dumps(job.get("tags", [])),
                job.get("apply_url", ""),
                job.get("created_at", ""),
                fetched_at,
            )
            for job in jobs
            if job.get("id")
        ]
        self.connection.executemany(
            """
            INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title, company_name=excluded.company_name,
                location=excluded.location, workplace=excluded.workplace,
                experience_level=excluded.experience_level,
                description=excluded.description, requirements=excluded.requirements,
                tags=excluded.tags, apply_url=excluded.apply_url,
                created_at=excluded.created_at, fetched_at=excluded.fetched_at
            """,
            rows,
        )
        self.connection.commit()
        return len(rows)

    def search(self, query: str = "", remote_only: bool = False, limit: int = 10) -> list[dict[str, Any]]:
        terms = f"%{query.lower()}%"
        sql = """
            SELECT * FROM jobs
            WHERE (lower(title) LIKE ? OR lower(company_name) LIKE ?
                OR lower(description) LIKE ? OR lower(tags) LIKE ?)
        """
        params: list[Any] = [terms, terms, terms, terms]
        if remote_only:
            sql += " AND lower(workplace) = 'remote'"
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return [self._job(dict(row)) for row in self.connection.execute(sql, params)]

    def all_jobs(self) -> list[dict[str, Any]]:
        return [self._job(dict(row)) for row in self.connection.execute("SELECT * FROM jobs")]

    def count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0])

    @staticmethod
    def _job(job: dict[str, Any]) -> dict[str, Any]:
        job["tags"] = json.loads(job["tags"])
        return job
