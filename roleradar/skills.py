from __future__ import annotations

import json
import re
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

_DATA = json.loads(Path(__file__).with_name("skills.json").read_text(encoding="utf-8"))

SKILLS: tuple[str, ...] = tuple(_DATA["skills"])
ALIASES: dict[str, str] = dict(_DATA["aliases"])
CATEGORIES: tuple[dict, ...] = tuple(_DATA["categories"])
CATEGORY_OF: dict[str, str] = {skill: item["name"] for item in CATEGORIES for skill in item["skills"]}
ROLE_OF: dict[str, str] = {item["name"]: item["role"] for item in CATEGORIES}

MIN_SKILL_CHARS = 2
MAX_SKILL_CHARS = 40
MAX_THEMES = 3
MAX_PROOF_POINTS = 4
_SKILL_SHAPE = re.compile(r"^[a-z0-9][a-z0-9+#.\- ]*$")


_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)


def normalize(text: str) -> str:
    return " ".join(re.sub(r"[-_/]", " ", _URL.sub(" ", text.lower())).split())


@lru_cache(maxsize=None)
def _pattern(term: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![\w+#]){re.escape(term)}(?![\w+#])")


def contains(normalized_text: str, term: str) -> bool:
    wanted = normalize(term)
    if not wanted or wanted not in normalized_text:
        return False
    return _pattern(wanted).search(normalized_text) is not None


@lru_cache(maxsize=None)
def _terms() -> dict[str, tuple[str, ...]]:
    table: dict[str, list[str]] = {skill: [skill] for skill in SKILLS}
    for alias, target in ALIASES.items():
        table.setdefault(target, [target]).append(alias)
    return {skill: tuple(terms) for skill, terms in table.items()}


@lru_cache(maxsize=None)
def _canonical_table() -> dict[str, str]:
    table = {normalize(alias): target for alias, target in ALIASES.items()}
    table.update({normalize(skill): skill for skill in SKILLS})
    return table


def terms_for(skill: str) -> tuple[str, ...]:
    return _terms().get(skill, (skill,))


def canonical(term: str) -> str:
    cleaned = normalize(term)
    return _canonical_table().get(cleaned, cleaned)


def skills_in(text: str, skills: Iterable[str]) -> list[str]:
    normalized = normalize(text)
    return [skill for skill in skills if any(contains(normalized, term) for term in terms_for(skill))]


def extract_vocab_skills(text: str) -> list[str]:
    return skills_in(text, SKILLS)


def clean_skill_list(raw: Iterable[str]) -> tuple[list[str], list[str]]:
    accepted: list[str] = []
    rejected: list[str] = []
    seen: set[str] = set()
    for item in raw:
        cleaned = " ".join(str(item).strip().lower().split())
        if not cleaned:
            continue
        if len(cleaned) < MIN_SKILL_CHARS:
            rejected.append(f"{cleaned} (too short to match safely)")
            continue
        if len(cleaned) > MAX_SKILL_CHARS or not _SKILL_SHAPE.match(cleaned) or cleaned.isdigit():
            rejected.append(f"{cleaned[:MAX_SKILL_CHARS]} (not a skill name)")
            continue
        skill = canonical(cleaned)
        if skill not in seen:
            seen.add(skill)
            accepted.append(skill)
    return accepted, rejected


def themes_for(skills: Iterable[str]) -> list[str]:
    counts: dict[str, int] = {}
    for skill in skills:
        category = CATEGORY_OF.get(skill)
        if category:
            counts[category] = counts.get(category, 0) + 1
    order = {item["name"]: index for index, item in enumerate(CATEGORIES)}
    ranked = sorted(counts, key=lambda name: (-counts[name], order[name]))
    return ranked[:MAX_THEMES]


def suggested_role(skills: Iterable[str]) -> str:
    themes = themes_for(skills)
    return ROLE_OF[themes[0]] if themes else ""


_METRIC = re.compile(
    r"\d+(?:[.,]\d+)?\s?%|[$€£₹]\s?\d|\b\d+(?:[.,]\d+)?\s?(?:x|k|m|million|billion|crore|lakh|users|customers|clients|requests|ms)\b",
    re.IGNORECASE,
)
_BULLET = re.compile(r"^[\s\-*•·▪●–—]+")


def _sentences(text: str) -> Iterable[str]:
    for line in re.split(r"[\r\n]+", text):
        start = 0
        for match in re.finditer(r"[.!?]+\s+", line):
            yield line[start : match.end()]
            start = match.end()
        yield line[start:]


def proof_points(text: str) -> list[str]:
    found: list[str] = []
    for sentence in _sentences(text):
        cleaned = " ".join(_BULLET.sub("", sentence).split())
        if not 25 <= len(cleaned) <= 240 or not _METRIC.search(cleaned):
            continue
        if cleaned not in found:
            found.append(cleaned)
        if len(found) == MAX_PROOF_POINTS:
            break
    return found
