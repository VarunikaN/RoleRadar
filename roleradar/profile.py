from __future__ import annotations

import ipaddress
import socket
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pypdf import PdfReader

from .skills import SKILLS, extract_vocab_skills, proof_points, suggested_role, themes_for

KNOWN_SKILLS = SKILLS

MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_LINK_BYTES = 2_000_000
MIN_RESUME_CHARS = 40
MIN_RESUME_WORDS = 8
TEXT_SUFFIXES = {"", ".txt", ".md", ".markdown", ".text"}
ALLOWED_LINK_TYPES = {"text/plain", "text/markdown", "text/x-markdown", "application/markdown"}


def extract_skills(text: str) -> list[str]:
    return extract_vocab_skills(text)


def profile_report(text: str) -> dict[str, list[str] | str]:
    skills = extract_skills(text)
    return {
        "headline": suggested_role(skills),
        "skills": skills,
        "pillars": themes_for(skills),
        "proof_points": proof_points(text),
    }


def check_resume_text(text: str) -> str:
    cleaned = text.replace("\x00", "").strip()
    if not cleaned:
        raise ValueError("That resume is empty.")
    printable = sum(1 for ch in cleaned if ch.isprintable() or ch in "\n\r\t")
    if printable / len(cleaned) < 0.95:
        raise ValueError("That file doesn't look like text. Use a text-based PDF, TXT, or Markdown resume.")
    letters = sum(1 for ch in cleaned if ch.isalpha())
    if len(cleaned) < MIN_RESUME_CHARS or len(cleaned.split()) < MIN_RESUME_WORDS:
        raise ValueError("That is too short to be a resume. Add a few lines of experience, projects, or skills.")
    if letters / len(cleaned) < 0.5:
        raise ValueError("That is mostly numbers or symbols, not resume text.")
    return cleaned


def normalize_resume_path(path: str) -> Path:
    cleaned = path.strip().strip("'").strip('"')
    if cleaned.startswith("file://"):
        cleaned = cleaned.removeprefix("file://")
    return Path(cleaned).expanduser()


def _read_pdf(file_path: Path) -> str:
    try:
        reader = PdfReader(file_path)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("That PDF is password-protected. Remove the password or paste the text instead.")
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(
            "I could not read that PDF. It may be corrupted or not a real PDF. "
            "Export a text-based PDF or paste the resume text instead."
        ) from error
    if not text:
        raise ValueError("That PDF does not contain readable text. Export a text-based PDF or paste the resume text instead.")
    return text


def read_resume_file(path: str) -> str:
    file_path = normalize_resume_path(path)
    if file_path.is_dir():
        raise ValueError(f"That path is a folder, not a file: {file_path}")
    if not file_path.is_file():
        raise ValueError(f"Resume file not found: {file_path}")
    suffix = file_path.suffix.lower()
    if suffix != ".pdf" and suffix not in TEXT_SUFFIXES:
        raise ValueError(f"Unsupported file type '{suffix}'. Use PDF, TXT, or Markdown.")
    if file_path.stat().st_size == 0:
        raise ValueError("That file is empty.")
    if file_path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("That file is larger than 8 MB. Use a smaller resume.")
    if suffix == ".pdf":
        return check_resume_text(_read_pdf(file_path))
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return check_resume_text(file_path.read_text(encoding=encoding))
        except UnicodeDecodeError:
            continue
    raise ValueError("I could not decode that file as text. Use PDF, TXT, or Markdown.")


def _is_public_host(hostname: str) -> bool:
    try:
        infos = socket.getaddrinfo(hostname, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ValueError(f"Could not find that host: {hostname}") from None
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address.is_multicast
            or address.is_unspecified
        ):
            return False
    return True


def _validate_link(url: str) -> str:
    if len(url) > 2048:
        raise ValueError("That link is too long.")
    parsed = urlparse(url.strip())
    if parsed.scheme != "https":
        raise ValueError("For privacy and safety, resume links must use HTTPS.")
    if not parsed.hostname:
        raise ValueError("That doesn't look like a valid link.")
    if not _is_public_host(parsed.hostname):
        raise ValueError("Links to private or local addresses are blocked.")
    return parsed.geturl()


class _SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_link(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_resume_link(url: str) -> str:
    safe_url = _validate_link(url)
    request = Request(safe_url, headers={"User-Agent": "RoleRadar/0.2"})
    try:
        with build_opener(_SafeRedirect).open(request, timeout=15) as response:
            content_type = response.headers.get_content_type()
            body = response.read(MAX_LINK_BYTES + 1)
    except HTTPError as error:
        if error.code == 404:
            raise ValueError("That link was not found (HTTP 404).") from None
        raise ValueError(f"That link returned HTTP {error.code}.") from None
    except (URLError, TimeoutError, OSError):
        raise ValueError("Could not reach that link. Check the address and your connection.") from None
    if len(body) > MAX_LINK_BYTES:
        raise ValueError("That link is larger than 2 MB. Use a smaller text resume.")
    if content_type == "application/pdf" or urlparse(safe_url).path.lower().endswith(".pdf"):
        raise ValueError("Download the PDF and use the upload option; remote PDF parsing is intentionally disabled.")
    if content_type == "text/html":
        raise ValueError("That link returns a web page, not resume text. Use a raw text or Markdown link, or upload the file.")
    if content_type not in ALLOWED_LINK_TYPES:
        raise ValueError(f"That link serves '{content_type}', not plain text or Markdown.")
    return check_resume_text(body.decode("utf-8", errors="replace"))
