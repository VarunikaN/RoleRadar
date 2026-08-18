from __future__ import annotations

import argparse
import os
import textwrap
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text
from rich.columns import Columns

from .profile import fetch_resume_link, profile_report, read_resume_file
from .service import match_jobs, sync, top_skills
from .store import JobStore

console = Console()
DATA_PATH = Path(os.environ.get("ROLERADAR_DATA_DIR", Path.home() / ".roleradar"))


def store() -> JobStore:
    DATA_PATH.mkdir(parents=True, exist_ok=True)
    return JobStore(DATA_PATH / "roleradar.db")


def banner() -> None:
    title = Text("ROLE", style="bold white")
    title.append("RADAR", style="bold bright_cyan")
    console.print()
    console.print(Panel.fit(title + "  [dim]resume-to-role matching[/dim]", border_style="bright_magenta", padding=(1, 4)))
    console.print("[dim]Parse a resume, extract verifiable skills, and rank live AI roles by listing overlap.[/dim]\n")


def job_table(jobs: list[dict], title: str = "Roles") -> None:
    table = Table(title=title, box=box.SIMPLE_HEAVY, header_style="bold bright_cyan", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Role", style="bold", min_width=26)
    table.add_column("Company", min_width=16)
    table.add_column("Workplace", width=10)
    table.add_column("Signals", min_width=24)
    for index, job in enumerate(jobs, start=1):
        matched = ", ".join(job.get("matched_skills", [])[:4])
        tags = matched or ", ".join(job.get("tags", [])[:4]) or "Not tagged"
        table.add_row(str(index), job["title"], job["company_name"], job.get("workplace", "-") or "-", tags)
    console.print(table)


def show_job(job: dict) -> None:
    skills = ", ".join(job.get("tags", [])) or "No tagged skills"
    description = (job.get("description") or job.get("requirements") or "No description available.").strip()
    body = (
        f"[bold bright_cyan]{job['company_name']}[/bold bright_cyan]  |  {job.get('location') or 'Location not listed'}\n"
        f"[dim]{job.get('workplace') or 'Workplace not listed'} | {job.get('experience_level') or 'Level not listed'}[/dim]\n\n"
        f"[bold]Skills:[/bold] {skills}\n"
        f"[bold]Apply:[/bold] {job.get('apply_url') or 'No application link listed'}\n\n"
        f"{textwrap.shorten(description, width=700, placeholder='...')}"
    )
    console.print(Panel(body, title=f"[bold]{job['title']}[/bold]", border_style="bright_cyan"))


def refresh(database: JobStore, include_india: bool = False) -> None:
    with console.status("[bright_cyan]Scanning live AI job sources...[/bright_cyan]", spinner="dots"):
        try:
            count = sync(database, include_india=include_india)
        except Exception as error:
            console.print(f"[yellow]Could not refresh live roles: {error}[/yellow]")
            return
    console.print(f"[green]Radar refreshed.[/green] Cached {count} live roles.")


def paste_resume() -> str:
    console.print("Paste your resume text now. When finished, type END on a line by itself.")
    lines: list[str] = []
    while True:
        line = input()
        if line.strip() == "END":
            return "\n".join(lines)
        lines.append(line)


def choose_resume_source() -> str:
    console.print(
        Panel(
            "[bold]1.[/bold] Load a local resume file\n"
            "[bold]2.[/bold] Paste resume text\n"
            "[bold]3.[/bold] Import a public HTTPS link\n"
            "[bold]4.[/bold] Start from manual skills only",
            title="[bold bright_cyan]Step 1 / Choose your source[/bold bright_cyan]",
            border_style="bright_magenta",
        )
    )
    answer = Prompt.ask("Select", choices=["1", "2", "3", "4"], default="1")
    return {"1": "file", "2": "paste", "3": "link", "4": "skills"}[answer]


def prompt_resume_file() -> str:
    console.print("Paste the full file path to your resume. Quoted paths and file:// paths are accepted.")
    console.print("Supported formats: PDF, TXT, and Markdown.")
    while True:
        source = Prompt.ask("Resume path").strip()
        if source.lower() in {"back", "cancel"}:
            return ""
        try:
            return read_resume_file(source)
        except Exception as error:
            console.print(f"[yellow]I could not read that file: {error}[/yellow]")
            if not Confirm.ask("Try another file path", default=True):
                return ""


def show_briefing(report: dict[str, list[str] | str], text: str) -> None:
    pillars = report["pillars"] or ["Machine learning"]
    proof_points = report["proof_points"] or ["Resume loaded, but I could not find measurable proof points yet."]
    preview = textwrap.shorten(" ".join(text.split()), width=220, placeholder="...")
    body = (
        f"[bold]{report['headline']}[/bold]\n\n"
        f"[bright_cyan]Themes[/bright_cyan]  {'  |  '.join(pillars)}\n\n"
        f"[bright_cyan]Proof[/bright_cyan]\n"
        + "\n".join(f"[green]•[/green] {point}" for point in proof_points)
        + f"\n\n[dim]Preview: {preview}[/dim]"
    )
    console.print(Panel(body, title="[bold bright_cyan]Step 2 / Evidence briefing[/bold bright_cyan]", border_style="green"))


def render_overview(skills: list[str], target: str, remote: bool, include_india: bool, report: dict[str, list[str] | str], database: JobStore) -> None:
    pillars = report.get("pillars", [])
    proof_points = report.get("proof_points", [])
    profile = Panel(
        f"[bold]{report['headline']}[/bold]\n"
        f"[dim]{target}[/dim]\n\n"
        f"[bright_cyan]Skills tracked[/bright_cyan]  {len(skills)}\n"
        f"[bright_cyan]Themes[/bright_cyan]  {len(pillars)}\n"
        f"[bright_cyan]Proof points[/bright_cyan]  {len(proof_points)}",
        title="[bold bright_magenta]Profile[/bold bright_magenta]",
        border_style="bright_magenta",
    )
    radar = Panel(
        f"[bright_cyan]Market[/bright_cyan]  {'India-aware' if include_india else 'Global AI jobs'}\n"
        f"[bright_cyan]Remote filter[/bright_cyan]  {'on' if remote else 'off'}\n"
        f"[bright_cyan]Cached roles[/bright_cyan]  {database.count()}\n"
        f"[bright_cyan]Data dir[/bright_cyan]  {DATA_PATH}",
        title="[bold bright_magenta]Radar[/bold bright_magenta]",
        border_style="bright_magenta",
    )
    commands = Panel(
        "/profile  review your evidence map\n"
        "/market   top demand signals\n"
        "/search   search a new role focus\n"
        "/open N   inspect a result\n"
        "/refresh  resync live jobs\n"
        "/quit     exit",
        title="[bold bright_magenta]Command bar[/bold bright_magenta]",
        border_style="bright_magenta",
    )
    console.print(Columns([profile, radar, commands], expand=True))


def show_market(database: JobStore) -> None:
    pulse = top_skills(database.all_jobs())
    if not pulse:
        console.print("[yellow]No market data cached yet.[/yellow]")
        return
    body = "\n".join(f"[bright_cyan]{skill:<18}[/bright_cyan] {count} active-role mentions" for skill, count in pulse)
    console.print(Panel(body, title="[bold bright_magenta]Market pulse[/bold bright_magenta]", border_style="bright_magenta"))


def introduce_candidate() -> tuple[list[str], bool, str, bool, dict[str, list[str] | str]]:
    console.print(
        Panel(
            "This session reads only the evidence already present in your resume. Nothing is uploaded or saved.\n"
            "If a file fails, you can retry immediately instead of restarting the whole flow.",
            title="[bold bright_cyan]Candidate intake[/bold bright_cyan]",
            border_style="bright_magenta",
        )
    )
    source = choose_resume_source()
    text = ""
    try:
        if source == "file":
            text = prompt_resume_file()
        elif source == "paste":
            text = paste_resume()
        elif source == "link":
            console.print("Paste a public HTTPS text or Markdown resume link. PDF links are still handled as local files.")
            text = fetch_resume_link(Prompt.ask("Resume link"))
    except Exception as error:
        console.print(f"[yellow]I could not read that resume: {error}[/yellow]")
    report = profile_report(text)
    skills = report["skills"]
    if text:
        show_briefing(report, text)
    else:
        console.print("[yellow]No resume evidence loaded, so the radar will rely on manual skills only.[/yellow]")
    console.print("\n[bold bright_cyan]Step 3 / Calibrate the search[/bold bright_cyan]")
    console.print("What role should I optimize for? Example: Applied AI Engineer")
    target = Prompt.ask("Target role", default=str(report["headline"]))
    console.print("Where can you work? Example: India, Hyderabad, remote worldwide")
    location = Prompt.ask("Location preference", default="India")
    console.print("What is your level?")
    level = Prompt.ask("Experience level", choices=["student", "junior", "mid", "senior"], default="student")
    console.print("Should I show only remote roles?")
    remote = Confirm.ask("Remote only", default=False)
    manual_default = ", ".join(skills[:8]) or "python, pytorch, llm, fastapi"
    manual = Prompt.ask("Add any skills the resume missed", default=manual_default)
    all_skills = list(dict.fromkeys(skills + [skill.strip().lower() for skill in manual.split(",") if skill.strip()]))
    console.print(
        Panel(
            f"[bright_cyan]Target[/bright_cyan]  {target}\n"
            f"[bright_cyan]Location[/bright_cyan]  {location}\n"
            f"[bright_cyan]Level[/bright_cyan]  {level}\n"
            f"[bright_cyan]Remote only[/bright_cyan]  {'yes' if remote else 'no'}\n"
            f"[bright_cyan]Tracked skills[/bright_cyan]  {', '.join(all_skills) or 'none'}",
            title="[bold bright_cyan]Step 4 / Radar settings[/bold bright_cyan]",
            border_style="bright_magenta",
        )
    )
    return all_skills, location.lower() == "india", target, remote, report


def interactive() -> None:
    database = store()
    banner()
    if database.count() == 0:
        refresh(database)
    skills, include_india, target, remote, report = introduce_candidate()
    if include_india and not os.getenv("ADZUNA_APP_ID"):
        console.print("[yellow]A note on India: the free AI-only source is US-heavy. Add free Adzuna credentials later to pull India-specific roles.[/yellow]")
    matches = match_jobs(database.search(target, remote, limit=30) or database.all_jobs(), skills)
    render_overview(skills, target, remote, include_india, report, database)
    if matches:
        job_table(matches, "Radar matches")
        for job in matches[:3]:
            console.print(
                Panel(
                    f"[bright_cyan]{job['match_score']}% fit[/bright_cyan]\n"
                    f"[bold]{job['title']}[/bold] at {job['company_name']}\n"
                    f"[green]Matched[/green]  {', '.join(job['matched_skills'])}\n"
                    f"[yellow]Build next[/yellow]  {', '.join(job['missing_skills']) or 'no tagged gaps'}",
                    border_style="green",
                )
            )
    else:
        console.print("[yellow]I found no supported matches in the current cache. Say refresh to scan again or try a broader target next time.[/yellow]")
    console.print("\n[dim]Use slash commands like /market, /search applied ai engineer, /open 1, /profile, /refresh, or /quit.[/dim]")
    while True:
        request = Prompt.ask("[bright_magenta]Command[/bright_magenta]").strip()
        normalized = request.lower()
        if normalized in {"quit", "exit", "done", "/quit"}:
            console.print("[bright_cyan]Exiting. The local job cache remains available for the next session.[/bright_cyan]")
            return
        if normalized in {"market", "/market"}:
            show_market(database)
        elif normalized in {"profile", "/profile"}:
            render_overview(skills, target, remote, include_india, report, database)
            if matches:
                job_table(matches, "Radar matches")
        elif normalized in {"refresh", "/refresh"}:
            refresh(database, include_india)
            matches = match_jobs(database.search(target, remote, limit=30) or database.all_jobs(), skills)
            if matches:
                job_table(matches, "Radar matches")
        elif normalized.startswith("search") or normalized.startswith("/search"):
            query = normalized.removeprefix("/search").removeprefix("search").strip() or target
            jobs = database.search(query, remote)
            scoped = match_jobs(jobs or database.all_jobs(), skills)
            if scoped:
                matches = scoped
                job_table(scoped, f"Results for: {query}")
            else:
                console.print("[yellow]No cached results for that focus.[/yellow]")
        elif normalized.startswith("open ") or normalized.startswith("/open "):
            index_text = normalized.removeprefix("/open ").removeprefix("open ").strip()
            if not index_text.isdigit():
                console.print("[yellow]Use /open 1 or /open 2.[/yellow]")
                continue
            index = int(index_text) - 1
            if index < 0 or index >= len(matches):
                console.print("[yellow]That result number is out of range.[/yellow]")
                continue
            show_job(matches[index])
        else:
            console.print("[dim]Try /market, /profile, /search computer vision, /open 1, /refresh, or /quit.[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser(description="RoleRadar AI job-market intelligence")
    parser.add_argument("--sync", action="store_true", help="Refresh the local job cache and exit")
    arguments = parser.parse_args()
    if arguments.sync:
        refresh(store())
        return
    interactive()
