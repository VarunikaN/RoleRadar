from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from pypdf import PdfReader

KNOWN_SKILLS = (
    "python", "c++", "sql", "pytorch", "tensorflow", "scikit-learn", "pandas", "numpy",
    "llm", "rag", "langchain", "langgraph", "fastapi", "docker", "kubernetes", "aws",
    "azure", "gcp", "postgresql", "redis", "git", "linux", "transformers", "opencv",
    "computer vision", "nlp", "machine learning", "deep learning", "cuda", "vllm", "llama.cpp",
)

PILLARS = {
    "LLM systems & efficiency": ("llm", "vllm", "llama.cpp", "quantization", "lora", "peft", "rag"),
    "Reliable AI applications": ("fastapi", "langchain", "langgraph", "prompt engineering", "agentic ai"),
    "Computer vision & robotics": ("computer vision", "opencv", "isaac sim", "blender", "deep learning"),
    "ML research & evaluation": ("pytorch", "tensorflow", "scikit-learn", "transformers", "shap"),
}


def extract_skills(text: str) -> list[str]:
    lowered = text.lower()
    return [skill for skill in KNOWN_SKILLS if re.search(rf"(?<![\w+]){re.escape(skill)}(?![\w+])", lowered)]


def profile_report(text: str) -> dict[str, list[str] | str]:
    """Create a concise, traceable candidate briefing from resume evidence."""
    skills = extract_skills(text)
    lowered = text.lower()
    pillars = [name for name, signals in PILLARS.items() if any(signal in lowered for signal in signals)]
    proof_points: list[str] = []
    evidence = (
        ("quantized reasoning model", "Quantized a reasoning model from 3.39 GB to 1.74 GB while measuring GSM8K and GPQA quality."),
        ("prompt-injection", "Built prompt-injection defenses and validation coverage for AI-agent interactions."),
        ("isaac sim", "Built physical-AI and sim-to-real workflows in Isaac Sim for robot manipulation."),
        ("91.86%", "Delivered compact segmentation research with 91.86% mIoU at 13.88M parameters."),
        ("100% recall@1", "Built a citation-grounded public-service navigator with 100% Recall@1 on representative cases."),
        ("37.5%", "Improved household electricity forecasting MAE by 37.5% against a seasonal baseline."),
    )
    for signal, point in evidence:
        if signal in lowered:
            proof_points.append(point)
    direction = "Applied AI Engineer"
    if "isaac sim" in lowered and "quantization" in lowered:
        direction = "Applied AI / ML Systems Engineer"
    return {
        "headline": direction,
        "skills": skills,
        "pillars": pillars or ["Machine learning"],
        "proof_points": proof_points[:4],
    }


def normalize_resume_path(path: str) -> Path:
    cleaned = path.strip().strip("'").strip('"')
    if cleaned.startswith("file://"):
        cleaned = cleaned.removeprefix("file://")
    return Path(cleaned).expanduser()


def read_resume_file(path: str) -> str:
    file_path = normalize_resume_path(path)
    if not file_path.is_file():
        raise ValueError(f"Resume file not found: {file_path}")
    if file_path.suffix.lower() == ".pdf":
        text = "\n".join(page.extract_text() or "" for page in PdfReader(file_path).pages).strip()
        if not text:
            raise ValueError("That PDF does not contain readable text. Export a text-based PDF or paste the resume text instead.")
        return text
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return file_path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("I could not decode that file as text. Use PDF, TXT, or Markdown.")


def fetch_resume_link(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("For privacy and safety, resume links must use HTTPS.")
    request = Request(url, headers={"User-Agent": "RoleRadar/0.2"})
    with urlopen(request, timeout=15) as response:
        content_type = response.headers.get_content_type()
        body = response.read(2_000_000)
    if content_type == "application/pdf" or parsed.path.lower().endswith(".pdf"):
        raise ValueError("Download the PDF and use the upload option; remote PDF parsing is intentionally disabled.")
    return body.decode("utf-8", errors="replace")
