import json
import sqlite3
from pathlib import Path
from urllib.error import HTTPError

import pytest

from roleradar import profile as profile_module
from roleradar import service, sources
from roleradar.profile import (
    check_resume_text,
    normalize_resume_path,
    profile_report,
    read_resume_file,
)
from roleradar.service import JobSourceError, find_roles, match_jobs, top_skills
from roleradar.skills import clean_skill_list, extract_vocab_skills
from roleradar.store import JobStore

PARITY = json.loads((Path(__file__).parent / "parity.json").read_text(encoding="utf-8"))

JOBS = [
    {
        "title": "Applied AI Engineer",
        "company_name": "Example",
        "description": "Build LLM services with Python and FastAPI.",
        "requirements": "PyTorch experience preferred.",
        "tags": ["python", "llm", "fastapi"],
        "created_at": "2026-08-18",
    }
]

RESUME = "Python engineer who built FastAPI services and trained PyTorch models for two years at a startup."


def job(job_id: str, title: str, **extra) -> dict:
    return {"id": job_id, "title": title, "company_name": "Co", "description": "", "tags": [], "created_at": job_id, **extra}


@pytest.fixture(autouse=True)
def fresh_sources_cache():
    sources.clear_cache()
    yield
    sources.clear_cache()


@pytest.fixture
def store(tmp_path) -> JobStore:
    return JobStore(tmp_path / "jobs.db")


def test_match_jobs_uses_job_evidence() -> None:
    matches = match_jobs(JOBS, ["python", "pytorch", "kubernetes"])
    assert matches[0]["matched_skills"] == ["python", "pytorch"]
    assert matches[0]["match_score"] == 67
    assert matches[0]["missing_skills"] == ["fastapi", "llm"]


def test_top_skills_counts_tags() -> None:
    counts = dict(top_skills(JOBS, limit=20))
    assert counts["python"] == counts["llm"] == counts["fastapi"] == counts["pytorch"] == 1


def test_profile_report_is_driven_by_the_resume_not_a_fixed_field() -> None:
    ml = profile_report("Trained PyTorch models and deployed them with Docker. Cut inference latency by 40% for 2M users.")
    assert ml["headline"] == "Machine Learning Engineer"
    assert "AI & machine learning" in ml["pillars"]
    assert ml["proof_points"] == ["Cut inference latency by 40% for 2M users."]

    nurse = profile_report("Registered nurse with patient care, triage and phlebotomy experience. Reduced wait times by 15%.")
    assert nurse["headline"] == "Registered Nurse"
    assert nurse["pillars"][0] == "Healthcare & life sciences"

    accountant = profile_report("Accountant skilled in bookkeeping, accounts payable, payroll and quickbooks. Saved $50,000 in audit fees.")
    assert accountant["headline"] == "Accountant"
    assert accountant["proof_points"] == ["Saved $50,000 in audit fees."]


def test_profile_without_known_skills_has_no_invented_role() -> None:
    report = profile_report("I enjoy long walks and quiet mornings with a good book.")
    assert report["headline"] == ""
    assert report["pillars"] == []
    assert report["proof_points"] == []


@pytest.mark.parametrize("case", PARITY["extract"], ids=lambda case: case["name"])
def test_extraction_parity_vectors(case) -> None:
    assert extract_vocab_skills(case["text"]) == case["skills"]


@pytest.mark.parametrize("case", PARITY["match"], ids=lambda case: case["name"])
def test_match_parity_vectors(case) -> None:
    matches = match_jobs([{"id": "1", **case["job"]}], case["skills"])
    if not case["matched"]:
        assert matches == []
        return
    assert matches[0]["matched_skills"] == case["matched"]
    assert matches[0]["match_score"] == case["score"]
    assert matches[0]["missing_skills"] == case["missing"]
    assert matches[0]["match_score"] == case["score"]
    assert matches[0]["missing_skills"] == case["missing"]


def test_empty_skill_list_matches_nothing() -> None:
    assert match_jobs(JOBS, []) == []
    assert match_jobs(JOBS, ["", "  "]) == []


def test_job_with_null_fields_does_not_crash() -> None:
    broken = {"id": "1", "title": None, "description": None, "requirements": None, "tags": None}
    assert match_jobs([broken], ["python"]) == []


def test_clean_skill_list_rejects_junk() -> None:
    accepted, rejected = clean_skill_list(["Torch", "r", "  ", "12345", "x" * 80, "<script>", "PyTorch", "c++"])
    assert accepted == ["pytorch", "c++"]
    assert len(rejected) == 4


def test_normalize_resume_path_handles_quotes_and_file_scheme(tmp_path) -> None:
    resume = tmp_path / "resume.md"
    resume.write_text(RESUME, encoding="utf-8")
    assert normalize_resume_path(f'"{resume}"') == resume
    assert normalize_resume_path(f"file://{resume}") == resume


def test_read_resume_file_accepts_quoted_path(tmp_path) -> None:
    resume = tmp_path / "resume.txt"
    resume.write_text(RESUME, encoding="utf-8")
    assert read_resume_file(f'"{resume}"') == RESUME


@pytest.mark.parametrize(
    ("name", "content", "message"),
    [
        ("empty.txt", b"", "empty"),
        ("short.txt", b"PyTorch and Docker", "too short"),
        ("binary.txt", bytes(range(256)) * 20, "doesn't look like text"),
        ("numbers.txt", b"1234 5678 " * 30, "numbers or symbols"),
        ("fake.pdf", b"this is not a pdf at all, just words " * 5, "could not read that PDF"),
        ("photo.png", b"\x89PNG\r\n\x1a\n" + b"x" * 100, "Unsupported file type"),
    ],
)
def test_bad_resume_files_get_a_clear_error(tmp_path, name, content, message) -> None:
    path = tmp_path / name
    path.write_bytes(content)
    with pytest.raises(ValueError, match=message):
        read_resume_file(str(path))


def test_folder_and_missing_paths_are_distinguished(tmp_path) -> None:
    with pytest.raises(ValueError, match="folder"):
        read_resume_file(str(tmp_path))
    with pytest.raises(ValueError, match="not found"):
        read_resume_file(str(tmp_path / "nope.pdf"))


def test_check_resume_text_accepts_a_normal_resume() -> None:
    assert check_resume_text(RESUME) == RESUME


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/resume.txt",
        "ftp://example.com/resume.txt",
        "https://localhost/resume.txt",
        "https://127.0.0.1/resume.txt",
        "https://169.254.169.254/latest/meta-data",
        "https://10.0.0.5/resume.txt",
        "https:///resume.txt",
        "not a url",
        "https://example.com/" + "a" * 3000,
    ],
)
def test_unsafe_or_invalid_links_are_blocked_before_any_request(url, monkeypatch) -> None:
    def forbid(*args, **kwargs):
        raise AssertionError("no network request should be made")

    monkeypatch.setattr(profile_module, "build_opener", forbid)
    with pytest.raises(ValueError):
        profile_module.fetch_resume_link(url)


class FakeResponse:
    def __init__(self, body: bytes, content_type: str = "text/plain") -> None:
        self._body = body
        self.headers = type("H", (), {"get_content_type": lambda self_: content_type})()

    def read(self, size: int = -1) -> bytes:
        return self._body[:size] if size >= 0 else self._body

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        return None


class FakeOpener:
    def __init__(self, outcome) -> None:
        self.outcome = outcome

    def open(self, request, timeout=None):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def patch_link(monkeypatch, outcome) -> None:
    monkeypatch.setattr(profile_module, "_is_public_host", lambda host: True)
    monkeypatch.setattr(profile_module, "build_opener", lambda *handlers: FakeOpener(outcome))


def test_link_returns_text(monkeypatch) -> None:
    patch_link(monkeypatch, FakeResponse(RESUME.encode()))
    assert profile_module.fetch_resume_link("https://example.com/resume.txt") == RESUME


@pytest.mark.parametrize(
    ("outcome", "message"),
    [
        (HTTPError("u", 404, "nf", None, None), "404"),
        (HTTPError("u", 500, "err", None, None), "HTTP 500"),
        (TimeoutError(), "Could not reach"),
        (FakeResponse(b"<html>hi</html>", "text/html"), "web page"),
        (FakeResponse(b"%PDF", "application/pdf"), "PDF"),
        (FakeResponse(b"{}", "application/json"), "application/json"),
        (FakeResponse(b"a" * (profile_module.MAX_LINK_BYTES + 5)), "larger than 2 MB"),
        (FakeResponse(b"hi"), "too short"),
    ],
)
def test_link_failures_are_explained(monkeypatch, outcome, message) -> None:
    patch_link(monkeypatch, outcome)
    with pytest.raises(ValueError, match=message):
        profile_module.fetch_resume_link("https://example.com/resume.txt")


def test_store_search_requires_every_word_not_the_exact_phrase(store) -> None:
    store.upsert_jobs([job("1", "Senior AI Engineer", tags=["python"]), job("2", "Chef")], "now")
    assert [row["id"] for row in store.search("engineer ai")] == ["1"]
    assert store.search("applied ai engineer") == []


def test_store_search_treats_wildcards_literally(store) -> None:
    store.upsert_jobs([job("1", "Machine Learning Engineer")], "now")
    assert store.search("%") == []
    assert store.search("_") == []
    assert store.search("'; DROP TABLE jobs; --") == []
    assert store.count() == 1


def test_store_survives_corrupt_tags_and_missing_fields(store) -> None:
    store.upsert_jobs([{"id": "1", "title": None, "company_name": None, "tags": None}], "now")
    store.connection.execute("UPDATE jobs SET tags = 'not json'")
    assert store.all_jobs()[0]["tags"] == []
    assert store.all_jobs()[0]["title"] == "Untitled role"


def test_store_level_groups(store) -> None:
    store.upsert_jobs(
        [job("1", "A", experience_level="senior"), job("2", "B", experience_level="lead"), job("3", "C", experience_level="junior")],
        "now",
    )
    assert {row["id"] for row in store.search(level="senior")} == {"1", "2"}
    assert {row["id"] for row in store.search(level="junior")} == {"3"}


def test_fetch_jobs_treats_null_jobs_as_empty(monkeypatch) -> None:
    monkeypatch.setattr(sources, "_read_json", lambda request, source: {"jobs": None, "total": 0})
    assert service.fetch_jobs("asdfgh") == []


def test_fetch_jobs_drops_malformed_entries(monkeypatch) -> None:
    payload = {"jobs": [{"id": "1", "title": "Ok"}, {"title": "no id"}, "text", None, {"id": "2"}]}
    monkeypatch.setattr(sources, "_read_json", lambda request, source: payload)
    assert [item["id"] for item in service.fetch_jobs()] == ["1"]


def test_fetch_jobs_sends_level_and_cleans_query(monkeypatch) -> None:
    seen = {}

    def capture(request, source):
        seen["url"] = request.full_url
        return {"jobs": []}

    monkeypatch.setattr(sources, "_read_json", capture)
    service.fetch_jobs("  ml    engineer  " + "x" * 300, level="senior")
    assert "level=senior" in seen["url"]
    assert "q=ml+engineer+" in seen["url"]
    assert len(seen["url"]) < 300
    service.fetch_jobs("ml", level="student")
    assert "level" not in seen["url"]


@pytest.mark.parametrize("case", PARITY["profile"], ids=lambda case: case["text"][:40])
def test_profile_parity_vectors(case) -> None:
    report = profile_report(case["text"])
    assert report["headline"] == case["headline"]
    assert report["pillars"] == case["pillars"]
    assert report["proof_points"] == case["proof_points"]


@pytest.mark.parametrize(
    ("code", "message"),
    [(429, "rate limiting"), (403, "rejected"), (500, "HTTP 500")],
)
def test_read_json_reports_http_errors(monkeypatch, code, message) -> None:
    def boom(request, timeout):
        raise HTTPError("u", code, "x", None, None)

    monkeypatch.setattr(sources, "urlopen", boom)
    with pytest.raises(JobSourceError, match=message):
        service.fetch_jobs("ml")


def test_read_json_reports_bad_json_and_network_errors(monkeypatch) -> None:
    class Bad:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, *args):
            return b"<html>"

    monkeypatch.setattr(sources, "urlopen", lambda request, timeout: Bad())
    with pytest.raises(JobSourceError, match="unreadable"):
        service.fetch_jobs("ml")

    def offline(request, timeout):
        raise OSError("down")

    monkeypatch.setattr(sources, "urlopen", offline)
    with pytest.raises(JobSourceError, match="Could not reach"):
        service.fetch_jobs("ml")


def test_adzuna_errors_do_not_leak_keys_or_fail_the_sync(monkeypatch, store) -> None:
    monkeypatch.setenv("ADZUNA_APP_ID", "secret-id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "secret-key")
    monkeypatch.setattr(service, "fetch_all", lambda *a, **k: ([job("1", "ML Engineer")], []))

    def boom(request, source):
        raise JobSourceError("Adzuna returned HTTP 500.")

    monkeypatch.setattr(sources, "_read_json", boom)
    result = service.sync(store, "ml", include_india=True)
    assert result.count == 1
    assert result.warnings == ["India listings skipped: Adzuna returned HTTP 500."]
    assert "secret" not in " ".join(result.warnings)


def test_india_without_keys_warns(monkeypatch, store) -> None:
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
    monkeypatch.setattr(service, "fetch_all", lambda *a, **k: ([], []))
    result = service.sync(store, include_india=True)
    assert "ADZUNA_APP_ID" in result.warnings[0]


def test_junk_target_role_finds_nothing_instead_of_ranking_everything(monkeypatch, store) -> None:
    store.upsert_jobs([job("1", "ML Engineer", description="python", tags=["python"])], "now")
    monkeypatch.setattr(service, "fetch_all", lambda *a, **k: ([], []))
    outcome = find_roles(store, "asdfghjkl", ["python"])
    assert outcome.roles_found == 0
    assert outcome.matches == []


def test_real_target_with_no_shared_skill_reports_zero_matches(monkeypatch, store) -> None:
    store.upsert_jobs([job("1", "Rust Engineer", description="rust and tokio", tags=["rust"])], "now")
    monkeypatch.setattr(service, "fetch_all", lambda *a, **k: ([], []))
    outcome = find_roles(store, "rust engineer", ["python"])
    assert outcome.roles_found == 1
    assert outcome.matches == []


def test_thin_cache_is_topped_up_from_the_live_api(monkeypatch, store) -> None:
    live = [job(str(index), "Applied AI Engineer", description="python", tags=["python"]) for index in range(6)]
    monkeypatch.setattr(service, "fetch_all", lambda *a, **k: (live, []))
    outcome = find_roles(store, "applied ai engineer", ["python"])
    assert outcome.roles_found == 6
    assert outcome.matches[0]["matched_skills"] == ["python"]


def test_offline_search_reports_why_and_keeps_cached_results(monkeypatch, store) -> None:
    store.upsert_jobs([job("1", "ML Engineer", description="python", tags=["python"])], "now")

    def offline(*args, **kwargs):
        raise JobSourceError("Could not reach the AI Dev Jobs API. Check your connection.")

    monkeypatch.setattr(service, "fetch_all", offline)
    outcome = find_roles(store, "ml engineer", ["python"])
    assert outcome.matches
    assert "Could not reach" in outcome.notes[0]


def test_level_with_no_listings_falls_back_with_a_note(monkeypatch, store) -> None:
    store.upsert_jobs([job("1", "ML Engineer", description="python", tags=["python"], experience_level="senior")] * 1, "now")
    monkeypatch.setattr(service, "fetch_all", lambda *a, **k: ([], []))
    outcome = find_roles(store, "ml engineer", ["python"], level="junior")
    assert outcome.matches
    assert "No junior-level roles" in outcome.notes[0]


def test_sqlite_errors_surface_as_sqlite_error(tmp_path) -> None:
    with pytest.raises(sqlite3.Error):
        JobStore(tmp_path / "missing" / "jobs.db")


def test_vocabulary_covers_every_field_and_is_consistent() -> None:
    from roleradar.skills import ALIASES, CATEGORIES, SKILLS

    assert len(SKILLS) == 398 and len(ALIASES) == 84 and len(CATEGORIES) == 21
    assert len(set(SKILLS)) == len(SKILLS)
    in_categories = [skill for category in CATEGORIES for skill in category["skills"]]
    assert sorted(in_categories) == sorted(SKILLS)
    assert all(target in SKILLS for target in ALIASES.values())
    assert all(category["role"] for category in CATEGORIES if category["name"] != "Business & management" or category["role"])


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Build dashboards in Power BI and Excel; SQL reporting", {"power bi", "sql"}),
        ("Manage accounts payable, payroll and quickbooks", {"accounts payable", "payroll", "quickbooks"}),
        ("Provide patient care, CPR certified, triage", {"patient care", "cpr", "triage"}),
        ("Ran SEO and email marketing campaigns", {"seo", "email marketing"}),
    ],
)
def test_extraction_works_outside_tech(text, expected) -> None:
    assert expected <= set(extract_vocab_skills(text))


def test_gaps_come_from_listing_text_when_there_are_no_tags() -> None:
    listing = {"title": "Accountant", "description": "We need payroll, quickbooks and accounts payable experience.", "tags": []}
    match = match_jobs([listing], ["payroll"])[0]
    assert match["match_score"] == 100
    assert match["missing_skills"] == ["accounts payable", "quickbooks"]
    assert dict(top_skills([listing], limit=5))["quickbooks"] == 1


def test_strip_html_keeps_text_and_drops_scripts() -> None:
    assert sources.strip_html("<p>Hi&nbsp;<b>there</b></p><script>x</script><li>one</li>") == "Hi there\none"
    assert sources.strip_html(None) == ""


def test_muse_categories_follow_the_role_title() -> None:
    assert sources.muse_categories("Accountant") == ["Accounting and Finance"]
    assert "Software Engineering" in sources.muse_categories("Applied AI Engineer")
    assert sources.muse_categories("zzzzqx") == []


MUSE_PAYLOAD = {
    "results": [
        {
            "id": 7, "name": "Staff Accountant", "contents": "<p>Own payroll and <b>quickbooks</b>.</p>",
            "locations": [{"name": "Flexible / Remote"}], "levels": [{"name": "Mid Level", "short_name": "mid"}],
            "company": {"name": "Acme"}, "refs": {"landing_page": "https://example.com/7"},
            "publication_date": "2026-09-01T00:00:00Z",
        },
        {"id": None, "name": ""},
    ]
}


def test_muse_listings_are_normalised(monkeypatch) -> None:
    monkeypatch.setattr(sources, "_read_json", lambda request, source: MUSE_PAYLOAD)
    jobs = sources.fetch_muse("accountant")
    assert len(jobs) == 1
    assert jobs[0]["source"] == "The Muse"
    assert jobs[0]["title"] == "Staff Accountant"
    assert jobs[0]["company_name"] == "Acme"
    assert "quickbooks" in jobs[0]["description"] and "<" not in jobs[0]["description"]
    assert jobs[0]["workplace"] == "remote"
    assert jobs[0]["apply_url"] == "https://example.com/7"


def test_arbeitnow_is_fetched_once_and_filtered_locally(monkeypatch) -> None:
    calls = []
    payload = {"data": [
        {"slug": "a", "title": "Nurse", "company_name": "H", "description": "<p>patient care</p>", "remote": False, "tags": [], "location": "Berlin", "url": "https://x/a", "created_at": 1790000000},
        {"slug": "b", "title": "Welder", "company_name": "F", "description": "mig welding", "remote": True, "tags": [], "location": "Hamburg", "url": "https://x/b", "created_at": 1790000001},
    ]}

    def fake(request, source):
        calls.append(source)
        return payload

    monkeypatch.setattr(sources, "_read_json", fake)
    assert [item["title"] for item in sources.fetch_arbeitnow("nurse")] == ["Nurse"]
    assert [item["title"] for item in sources.fetch_arbeitnow("welder")] == ["Welder"]
    assert len(calls) == 1
    assert sources.fetch_arbeitnow("welder", remote_only=True)[0]["workplace"] == "remote"


def test_fetch_all_survives_one_source_failing_and_reports_it(monkeypatch) -> None:
    def broken(*args, **kwargs):
        raise JobSourceError("The Muse returned HTTP 500.")

    monkeypatch.setitem(sources.SOURCES, "muse", ("The Muse", broken))
    monkeypatch.setitem(sources.SOURCES, "aidev", ("AI Dev Jobs", lambda *a, **k: [job("1", "Analyst")]))
    monkeypatch.setitem(sources.SOURCES, "arbeitnow", ("Arbeitnow", lambda *a, **k: [job("1", "Analyst"), job("2", "Clerk")]))
    jobs, warnings = sources.fetch_all("analyst")
    assert sorted(item["id"] for item in jobs) == ["1", "2"]
    assert warnings == ["The Muse returned HTTP 500."]


def test_fetch_all_fails_only_when_every_source_fails(monkeypatch) -> None:
    def broken(*args, **kwargs):
        raise JobSourceError("down")

    for key, (label, _) in list(sources.SOURCES.items()):
        monkeypatch.setitem(sources.SOURCES, key, (label, broken))
    with pytest.raises(JobSourceError):
        sources.fetch_all("analyst")


def test_old_database_gets_the_source_column(tmp_path) -> None:
    path = tmp_path / "old.db"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE jobs (id TEXT PRIMARY KEY, title TEXT NOT NULL, company_name TEXT NOT NULL, location TEXT, workplace TEXT, "
        "experience_level TEXT, description TEXT, requirements TEXT, tags TEXT, apply_url TEXT, created_at TEXT, fetched_at TEXT NOT NULL)"
    )
    connection.commit()
    connection.close()
    migrated = JobStore(path)
    migrated.upsert_jobs([job("1", "Analyst", source="The Muse")], "now")
    assert migrated.search("analyst")[0]["source"] == "The Muse"


def test_query_words_must_start_a_word_not_sit_inside_one() -> None:
    listing = {"title": "Maintenance Technician", "description": "Maintain equipment", "tags": []}
    assert not sources.query_matches(listing, "ai")
    assert sources.query_matches({"title": "Applied AI Engineer"}, "ai engineer")
    assert sources.query_matches({"title": "Registered Nurses"}, "nurse")
    assert sources.query_matches(listing, "")


def test_listings_with_markup_lookalikes_do_not_crash_the_terminal(capsys) -> None:
    from roleradar import cli

    hostile = job("1", "Nurse [/bold] [red]URGENT[/red] [Remote]", company_name="[link=x]Co[/link]", description="[/] patient care", source="The [Muse]", tags=["nursing"])
    cli.job_table([hostile], "Results for: [/x]")
    cli.show_job(hostile)
    output = capsys.readouterr().out
    assert "[Remote]" in output and "[/bold]" in output
