from roleradar.service import match_jobs, top_skills
from roleradar.profile import normalize_resume_path, profile_report, read_resume_file


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


def test_match_jobs_uses_job_evidence() -> None:
    matches = match_jobs(JOBS, ["python", "pytorch", "kubernetes"])
    assert matches[0]["matched_skills"] == ["python", "pytorch"]
    assert matches[0]["match_score"] == 67
    assert matches[0]["missing_skills"] == ["fastapi", "llm"]


def test_top_skills_counts_tags() -> None:
    assert top_skills(JOBS)[:2] == [("python", 1), ("llm", 1)]


def test_profile_report_surfaces_resume_evidence() -> None:
    report = profile_report("Quantization with llama.cpp and vLLM. Built prompt-injection guardrails in Isaac Sim. Achieved 91.86% mIoU.")
    assert report["headline"] == "Applied AI / ML Systems Engineer"
    assert "LLM systems & efficiency" in report["pillars"]
    assert "Computer vision & robotics" in report["pillars"]
    assert len(report["proof_points"]) == 3


def test_normalize_resume_path_handles_quotes_and_file_scheme(tmp_path) -> None:
    resume = tmp_path / "resume.md"
    resume.write_text("Python FastAPI", encoding="utf-8")
    assert normalize_resume_path(f'"{resume}"') == resume
    assert normalize_resume_path(f"file://{resume}") == resume


def test_read_resume_file_accepts_quoted_path(tmp_path) -> None:
    resume = tmp_path / "resume.txt"
    resume.write_text("PyTorch and Docker", encoding="utf-8")
    assert read_resume_file(f'"{resume}"') == "PyTorch and Docker"
