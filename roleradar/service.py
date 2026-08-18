from __future__ import annotations

import json
import os
from collections import Counter
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .store import JobStore

API_URL = "https://aidevboard.com/api/v1/jobs"
ADZUNA_URL = "https://api.adzuna.com/v1/api/jobs"


def fetch_jobs(query: str = "", remote_only: bool = False, limit: int = 50) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"limit": min(limit, 50)}
    if query:
        params["q"] = query
    if remote_only:
        params["workplace"] = "remote"
    request = Request(f"{API_URL}?{urlencode(params)}", headers={"User-Agent": "RoleRadar/0.1"})
    with urlopen(request, timeout=20) as response:
        payload = json.load(response)
    return payload.get("jobs", [])


def fetch_india_jobs(query: str = "AI engineer", limit: int = 50) -> list[dict[str, Any]]:
    """Fetch Indian roles only when the user has configured their own Adzuna key."""
    app_id, app_key = os.getenv("ADZUNA_APP_ID"), os.getenv("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        return []
    params = {"app_id": app_id, "app_key": app_key, "what": query, "results_per_page": min(limit, 50)}
    request = Request(f"{ADZUNA_URL}/in/search/1?{urlencode(params)}", headers={"User-Agent": "RoleRadar/0.2"})
    with urlopen(request, timeout=20) as response:
        results = json.load(response).get("results", [])
    return [
        {
            "id": f"adzuna-{job['id']}", "title": job.get("title", "Untitled role"),
            "company_name": job.get("company", {}).get("display_name", "Unknown company"),
            "description": job.get("description", ""), "requirements": "",
            "location": job.get("location", {}).get("display_name", "India"), "workplace": "onsite or unspecified",
            "experience_level": "", "tags": [], "apply_url": job.get("redirect_url", ""),
            "created_at": job.get("created", ""),
        }
        for job in results
    ]


def sync(store: JobStore, query: str = "", remote_only: bool = False, include_india: bool = False) -> int:
    jobs = fetch_jobs(query, remote_only)
    if include_india:
        jobs.extend(fetch_india_jobs(query or "AI engineer"))
    return store.upsert_jobs(jobs, datetime.now(UTC).isoformat())


def match_jobs(jobs: list[dict[str, Any]], skills: list[str], limit: int = 8) -> list[dict[str, Any]]:
    normalized_skills = {skill.strip().lower() for skill in skills if skill.strip()}
    matches: list[dict[str, Any]] = []
    for job in jobs:
        text = " ".join(
            [job.get("title", ""), job.get("description", ""), job.get("requirements", ""), " ".join(job.get("tags", []))]
        ).lower()
        matched = sorted(skill for skill in normalized_skills if skill in text)
        if not matched:
            continue
        job = job.copy()
        job["matched_skills"] = matched
        job["match_score"] = round(100 * len(matched) / max(len(normalized_skills), 1))
        job_tags = {tag.lower() for tag in job.get("tags", [])}
        job["missing_skills"] = sorted(tag for tag in job_tags if tag and tag not in normalized_skills)[:6]
        matches.append(job)
    return sorted(matches, key=lambda job: (job["match_score"], job.get("created_at", "")), reverse=True)[:limit]


def top_skills(jobs: list[dict[str, Any]], limit: int = 8) -> list[tuple[str, int]]:
    tags = Counter(tag.lower() for job in jobs for tag in job.get("tags", []))
    return tags.most_common(limit)
