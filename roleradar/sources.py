from __future__ import annotations

import html
import json
import os
import re
import time
from datetime import datetime, timezone
from http.client import HTTPException
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

USER_AGENT = "RoleRadar/0.3 (+https://github.com/VarunikaN/RoleRadar)"
AIDEV_URL = "https://aidevboard.com/api/v1/jobs"
ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"
MUSE_URL = "https://www.themuse.com/api/public/jobs"
ADZUNA_URL = "https://api.adzuna.com/v1/api/jobs"
MAX_QUERY_CHARS = 100
MAX_DESCRIPTION_CHARS = 20_000
ARBEITNOW_TTL_SECONDS = 3600
LEVELS = {"junior", "mid", "senior"}
MUSE_LEVELS = {"junior": "Entry Level", "mid": "Mid Level", "senior": "Senior Level"}
MUSE_LEVEL_NAMES = {"Entry Level": "junior", "Mid Level": "mid", "Senior Level": "senior"}

MUSE_CATEGORY_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("software", "developer", "programmer", "backend", "frontend", "full stack", "devops", "machine learning", "ml", "ai", "llm"), "Software Engineering"),
    (("data", "analyst", "analytics", "business intelligence", "scientist"), "Data and Analytics"),
    (("design", "ux", "ui", "graphic", "creative"), "Design and UX"),
    (("marketing", "seo", "content", "brand", "social media", "advertising"), "Advertising and Marketing"),
    (("sales", "business development", "account executive"), "Sales"),
    (("account manager", "client success", "customer success"), "Account Management"),
    (("accountant", "accounting", "finance", "financial", "audit", "auditor", "tax", "payroll", "bookkeeper"), "Accounting and Finance"),
    (("hr", "human resources", "recruiter", "recruiting", "talent", "people operations"), "Human Resources and Recruitment"),
    (("nurse", "nursing", "doctor", "physician", "clinical", "medical", "health", "pharmacist", "therapist", "dental"), "Healthcare"),
    (("teacher", "tutor", "professor", "instructor", "education", "curriculum"), "Education"),
    (("product manager", "product management", "product owner"), "Product Management"),
    (("project manager", "program manager", "scrum master"), "Project Management"),
    (("operations", "administrator", "administrative", "coordinator", "office"), "Business Operations"),
    (("customer service", "customer support", "support specialist", "help desk"), "Customer Service"),
    (("legal", "lawyer", "attorney", "paralegal", "counsel", "compliance"), "Legal Services"),
    (("retail", "store", "cashier", "merchandis"), "Retail"),
    (("warehouse", "manufacturing", "production", "assembler"), "Manufacturing and Warehouse"),
    (("logistics", "supply chain", "driver", "dispatcher", "transportation"), "Transportation and Logistics"),
    (("technician", "mechanic", "electrician", "plumber", "hvac", "maintenance", "installer"), "Installation, Maintenance, and Repairs"),
    (("writer", "editor", "journalist", "copywriter"), "Writing and Editing"),
    (("chef", "cook", "restaurant", "hospitality", "hotel", "server", "barista"), "Food and Hospitality Services"),
    (("construction", "contractor"), "Construction"),
    (("it support", "sysadmin", "system administrator", "network", "security analyst", "cybersecurity"), "Computer and IT"),
    (("engineer", "engineering", "scientist", "research"), "Science and Engineering"),
    (("manager", "director", "head of"), "Management"),
)


class JobSourceError(RuntimeError):
    pass


def clean_query(query: str) -> str:
    return " ".join(query.split())[:MAX_QUERY_CHARS]


def _read_json(request: Request, source: str) -> Any:
    try:
        with urlopen(request, timeout=20) as response:
            return json.load(response)
    except HTTPError as error:
        if error.code == 429:
            raise JobSourceError(f"{source} is rate limiting requests (HTTP 429). Try again in a minute.") from None
        if error.code in {401, 403}:
            raise JobSourceError(f"{source} rejected the request (HTTP {error.code}).") from None
        raise JobSourceError(f"{source} returned HTTP {error.code}.") from None
    except (URLError, TimeoutError, OSError, HTTPException):
        raise JobSourceError(f"Could not reach {source}. Check your connection.") from None
    except ValueError:
        raise JobSourceError(f"{source} returned an unreadable response.") from None


_DROP = re.compile(r"<(script|style)\b.*?</\1>", re.IGNORECASE | re.DOTALL)
_BLOCK = re.compile(r"</?(?:p|div|br|li|ul|ol|h[1-6]|tr|td|table|section|article)\b[^>]*>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")


def strip_html(text: Any) -> str:
    value = _DROP.sub(" ", str(text or ""))
    value = html.unescape(_TAG.sub(" ", _BLOCK.sub("\n", value)))
    lines = (" ".join(line.split()) for line in value.splitlines())
    return "\n".join(line for line in lines if line)[:MAX_DESCRIPTION_CHARS]


def query_matches(job: dict[str, Any], query: str) -> bool:
    words = query.lower().split()
    if not words:
        return True
    haystack = " ".join(
        [str(job.get("title") or ""), str(job.get("company_name") or ""), str(job.get("description") or ""), " ".join(map(str, job.get("tags") or []))]
    ).lower()
    return all(re.search(rf"(?<![\w+#]){re.escape(word)}", haystack) for word in words)


def _valid_jobs(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    return [job for job in items if isinstance(job, dict) and job.get("id") and job.get("title")]


def fetch_aidev(query: str = "", remote_only: bool = False, limit: int = 50, level: str | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"limit": max(1, min(limit, 50))}
    query = clean_query(query)
    if query:
        params["q"] = query
    if remote_only:
        params["workplace"] = "remote"
    if level in LEVELS:
        params["level"] = level
    request = Request(f"{AIDEV_URL}?{urlencode(params)}", headers={"User-Agent": USER_AGENT})
    payload = _read_json(request, "the AI Dev Jobs API")
    if not isinstance(payload, dict):
        raise JobSourceError("The AI Dev Jobs API returned an unexpected response.")
    jobs = _valid_jobs(payload.get("jobs"))
    for job in jobs:
        job["description"] = strip_html(job.get("description"))
        job["requirements"] = strip_html(job.get("requirements"))
        job["source"] = "AI Dev Jobs"
    return jobs


_arbeitnow_cache: tuple[float, list[dict[str, Any]]] | None = None


def clear_cache() -> None:
    global _arbeitnow_cache
    _arbeitnow_cache = None


def _iso(epoch: Any) -> str:
    try:
        return datetime.fromtimestamp(int(epoch), timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def _arbeitnow_all() -> list[dict[str, Any]]:
    global _arbeitnow_cache
    now = time.monotonic()
    if _arbeitnow_cache and now - _arbeitnow_cache[0] < ARBEITNOW_TTL_SECONDS:
        return _arbeitnow_cache[1]
    payload = _read_json(Request(ARBEITNOW_URL, headers={"User-Agent": USER_AGENT}), "Arbeitnow")
    items = payload.get("data") if isinstance(payload, dict) else None
    jobs = [
        {
            "id": f"arbeitnow-{item['slug']}",
            "title": str(item["title"]),
            "company_name": str(item.get("company_name") or "Unknown company"),
            "description": strip_html(item.get("description")),
            "requirements": "",
            "location": str(item.get("location") or ""),
            "workplace": "remote" if item.get("remote") else "onsite or unspecified",
            "experience_level": "",
            "tags": [],
            "apply_url": str(item.get("url") or ""),
            "created_at": _iso(item.get("created_at")),
            "source": "Arbeitnow",
        }
        for item in (items if isinstance(items, list) else [])
        if isinstance(item, dict) and item.get("slug") and item.get("title")
    ]
    _arbeitnow_cache = (now, jobs)
    return jobs


def fetch_arbeitnow(query: str = "", remote_only: bool = False, limit: int = 50, level: str | None = None) -> list[dict[str, Any]]:
    query = clean_query(query)
    jobs = [job for job in _arbeitnow_all() if query_matches(job, query) and (not remote_only or job["workplace"] == "remote")]
    return jobs[: max(1, limit)]


def muse_categories(query: str) -> list[str]:
    lowered = f" {' '.join(re.findall(r'[a-z0-9+#]+', query.lower()))} "
    found: list[str] = []
    for keywords, category in MUSE_CATEGORY_HINTS:
        if any(f" {word} " in lowered or (" " not in word and len(word) > 4 and word in lowered) for word in keywords):
            if category not in found:
                found.append(category)
    return found[:2]


def _muse_job(item: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(item, dict) or not item.get("id") or not item.get("name"):
        return None
    names = [str(place.get("name") or "") for place in item.get("locations") or [] if isinstance(place, dict)]
    remote = any("remote" in name.lower() or "flexible" in name.lower() for name in names)
    levels = [str(entry.get("name") or "") for entry in item.get("levels") or [] if isinstance(entry, dict)]
    level = next((MUSE_LEVEL_NAMES[name] for name in levels if name in MUSE_LEVEL_NAMES), "")
    return {
        "id": f"muse-{item['id']}",
        "title": str(item["name"]),
        "company_name": str((item.get("company") or {}).get("name") or "Unknown company"),
        "description": strip_html(item.get("contents")),
        "requirements": "",
        "location": ", ".join(name for name in names if name),
        "workplace": "remote" if remote else "onsite or unspecified",
        "experience_level": level,
        "tags": [],
        "apply_url": str((item.get("refs") or {}).get("landing_page") or ""),
        "created_at": str(item.get("publication_date") or ""),
        "source": "The Muse",
    }


def fetch_muse(query: str = "", remote_only: bool = False, limit: int = 50, level: str | None = None) -> list[dict[str, Any]]:
    query = clean_query(query)
    categories: list[str | None] = list(muse_categories(query)) or [None]
    jobs: dict[str, dict[str, Any]] = {}
    for category in categories:
        for page in (1, 2):
            params: dict[str, Any] = {"page": page}
            if category:
                params["category"] = category
            if level in MUSE_LEVELS:
                params["level"] = MUSE_LEVELS[level]
            request = Request(f"{MUSE_URL}?{urlencode(params)}", headers={"User-Agent": USER_AGENT})
            payload = _read_json(request, "The Muse")
            results = payload.get("results") if isinstance(payload, dict) else None
            for item in results if isinstance(results, list) else []:
                job = _muse_job(item)
                if job and query_matches(job, query) and (not remote_only or job["workplace"] == "remote"):
                    jobs.setdefault(job["id"], job)
    return list(jobs.values())[: max(1, limit)]


SOURCES: dict[str, tuple[str, Callable[..., list[dict[str, Any]]]]] = {
    "aidev": ("AI Dev Jobs", fetch_aidev),
    "arbeitnow": ("Arbeitnow", fetch_arbeitnow),
    "muse": ("The Muse", fetch_muse),
}


def fetch_all(
    query: str = "",
    remote_only: bool = False,
    level: str | None = None,
    limit: int = 30,
) -> tuple[list[dict[str, Any]], list[str]]:
    jobs: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    answered = 0
    for label, fetcher in SOURCES.values():
        try:
            for job in fetcher(query, remote_only, limit, level):
                jobs.setdefault(str(job["id"]), job)
            answered += 1
        except JobSourceError as error:
            warnings.append(str(error))
    if answered == 0:
        raise JobSourceError(" ".join(warnings) or "No job source answered.")
    return list(jobs.values()), warnings


def adzuna_configured() -> bool:
    return bool(os.getenv("ADZUNA_APP_ID") and os.getenv("ADZUNA_APP_KEY"))


def fetch_india_jobs(query: str = "", limit: int = 50) -> list[dict[str, Any]]:
    if not adzuna_configured():
        return []
    params = {
        "app_id": os.environ["ADZUNA_APP_ID"],
        "app_key": os.environ["ADZUNA_APP_KEY"],
        "results_per_page": max(1, min(limit, 50)),
    }
    if clean_query(query):
        params["what"] = clean_query(query)
    request = Request(f"{ADZUNA_URL}/in/search/1?{urlencode(params)}", headers={"User-Agent": USER_AGENT})
    payload = _read_json(request, "Adzuna")
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return []
    return [
        {
            "id": f"adzuna-{job['id']}", "title": job.get("title", "Untitled role"),
            "company_name": (job.get("company") or {}).get("display_name", "Unknown company"),
            "description": strip_html(job.get("description")), "requirements": "",
            "location": (job.get("location") or {}).get("display_name", "India"), "workplace": "onsite or unspecified",
            "experience_level": "", "tags": [], "apply_url": job.get("redirect_url", ""),
            "created_at": job.get("created", ""), "source": "Adzuna",
        }
        for job in results
        if isinstance(job, dict) and job.get("id")
    ]
