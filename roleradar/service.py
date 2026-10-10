from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from . import sources
from .skills import canonical, extract_vocab_skills, normalize, skills_in
from .sources import (
    JobSourceError,
    adzuna_configured,
    clean_query,
    fetch_aidev,
    fetch_all,
    fetch_india_jobs,
)
from .store import JobStore

fetch_jobs = fetch_aidev
LEVELS = sources.LEVELS


@dataclass
class SyncResult:
    count: int
    warnings: list[str] = field(default_factory=list)


def sync(
    store: JobStore,
    query: str = "",
    remote_only: bool = False,
    include_india: bool = False,
    level: str | None = None,
) -> SyncResult:
    jobs, warnings = fetch_all(query, remote_only, level)
    if include_india:
        if not adzuna_configured():
            warnings.append("India listings skipped: set ADZUNA_APP_ID and ADZUNA_APP_KEY to enable them.")
        else:
            try:
                jobs.extend(fetch_india_jobs(query))
            except JobSourceError as error:
                warnings.append(f"India listings skipped: {error}")
    return SyncResult(store.upsert_jobs(jobs, datetime.now(timezone.utc).isoformat()), warnings)


@dataclass
class SearchOutcome:
    matches: list[dict[str, Any]]
    roles_found: int
    notes: list[str] = field(default_factory=list)


MIN_CACHED_ROLES = 5
SEARCH_LIMIT = 60


def find_roles(
    store: JobStore,
    target: str,
    skills: list[str],
    remote_only: bool = False,
    level: str | None = None,
    include_india: bool = False,
    live: bool = True,
) -> SearchOutcome:
    query = clean_query(target)
    notes: list[str] = []
    roles = store.search(query, remote_only, limit=SEARCH_LIMIT, level=level)
    if live and len(roles) < MIN_CACHED_ROLES:
        try:
            notes.extend(sync(store, query, remote_only, include_india, level).warnings)
        except JobSourceError as error:
            notes.append(str(error))
        roles = store.search(query, remote_only, limit=SEARCH_LIMIT, level=level)
    if not roles and level in LEVELS:
        roles = store.search(query, remote_only, limit=SEARCH_LIMIT)
        if roles:
            notes.append(f"No {level}-level roles listed for '{query}'; showing every level.")
    return SearchOutcome(match_jobs(roles, skills), len(roles), notes)


def match_jobs(jobs: list[dict[str, Any]], skills: list[str], limit: int = 8) -> list[dict[str, Any]]:
    candidate = list(dict.fromkeys(canonical(skill) for skill in skills if skill and skill.strip()))
    if not candidate:
        return []
    matches: list[dict[str, Any]] = []
    for job in jobs:
        matched = sorted(skills_in(job_text(job), candidate))
        if not matched:
            continue
        job = job.copy()
        job["matched_skills"] = matched
        job["match_score"] = int(100 * len(matched) / len(candidate) + 0.5)
        job["missing_skills"] = sorted(job_skills(job) - set(candidate))[:6]
        matches.append(job)
    return sorted(matches, key=lambda job: (job["match_score"], job.get("created_at") or ""), reverse=True)[:limit]


def job_text(job: dict[str, Any]) -> str:
    tags = " ".join(str(tag) for tag in (job.get("tags") or []))
    return " ".join([str(job.get("title") or ""), str(job.get("description") or ""), str(job.get("requirements") or ""), tags])


def job_skills(job: dict[str, Any]) -> set[str]:
    tags = {canonical(str(tag)) for tag in (job.get("tags") or []) if normalize(str(tag))}
    return tags | set(extract_vocab_skills(job_text(job)))


def top_skills(jobs: list[dict[str, Any]], limit: int = 8) -> list[tuple[str, int]]:
    counts = Counter(skill for job in jobs for skill in job_skills(job))
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
