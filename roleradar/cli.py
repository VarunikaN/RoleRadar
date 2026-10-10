from __future__ import annotations

import argparse
import os
import textwrap
from pathlib import Path

from rich import box
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text
from rich.columns import Columns

import sqlite3
import sys

from .profile import check_resume_text, fetch_resume_link, profile_report, read_resume_file
from .service import (
    JobSourceError,
    adzuna_configured,
    clean_query,
    find_roles,
    job_skills,
    sync,
    top_skills,
)
from .skills import clean_skill_list
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
    title.append("  resume-to-role matching", style="dim")
    console.print(Panel.fit(title, border_style="bright_magenta", padding=(1, 4)))
    console.print("[dim]Parse a resume, extract verifiable skills, and rank live roles in any field by listing overlap.[/dim]\n")


def job_table(jobs: list[dict], title: str = "Roles") -> None:
    table = Table(title=escape(title), box=box.SIMPLE_HEAVY, header_style="bold bright_cyan", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Role", style="bold", min_width=26)
    table.add_column("Company", min_width=16)
    table.add_column("Workplace", width=10)
    table.add_column("Source", width=12)
    table.add_column("Signals", min_width=24)
    for index, job in enumerate(jobs, start=1):
        matched = ", ".join(job.get("matched_skills", [])[:4])
        tags = matched or ", ".join(job.get("tags", [])[:4]) or "No skills detected"
        table.add_row(
            str(index), escape(job["title"]), escape(job.get("company_name") or "Unknown company"),
            escape(job.get("workplace", "-") or "-"), escape(job.get("source") or "-"), escape(tags),
        )
    console.print(table)


def show_job(job: dict) -> None:
    skills = ", ".join(sorted(job_skills(job))) or "No known skills detected in the listing"
    description = (job.get("description") or job.get("requirements") or "No description available.").strip()
    body = (
        f"[bold bright_cyan]{escape(job.get('company_name') or 'Unknown company')}[/bold bright_cyan]  |  {escape(job.get('location') or 'Location not listed')}\n"
        f"[dim]{escape(job.get('workplace') or 'Workplace not listed')} | {escape(job.get('experience_level') or 'Level not listed')} | via {escape(job.get('source') or 'unknown source')}[/dim]\n\n"
        f"[bold]Skills:[/bold] {escape(skills)}\n"
        f"[bold]Apply:[/bold] {escape(job.get('apply_url') or 'No application link listed')}\n\n"
        f"{escape(textwrap.shorten(description, width=700, placeholder='...'))}"
    )
    console.print(Panel(body, title=f"[bold]{escape(job['title'])}[/bold]", border_style="bright_cyan"))


def refresh(database: JobStore, include_india: bool = False) -> None:
    with console.status("[bright_cyan]Scanning live job sources...[/bright_cyan]", spinner="dots"):
        try:
            result = sync(database, include_india=include_india)
        except JobSourceError as error:
            console.print(f"[yellow]Could not refresh live roles: {error}[/yellow]")
            return
    for warning in result.warnings:
        console.print(f"[yellow]{warning}[/yellow]")
    console.print(f"[green]Radar refreshed.[/green] Cached {result.count} live roles.")


def paste_resume() -> str:
    console.print("Paste your resume text now. When finished, type END on a line by itself.")
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            return check_resume_text("\n".join(lines))
        if line.strip() == "END":
            return check_resume_text("\n".join(lines))
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
        except (ValueError, OSError) as error:
            console.print(f"[yellow]I could not read that file: {error}[/yellow]")
            if not Confirm.ask("Try another file path", default=True):
                return ""


def show_briefing(report: dict[str, list[str] | str], text: str) -> None:
    pillars = report["pillars"] or ["No clear field detected yet"]
    proof_points = report["proof_points"] or ["No sentence with a measurable result (a %, an amount, a count) was found in the resume."]
    preview = textwrap.shorten(" ".join(text.split()), width=220, placeholder="...")
    body = (
        f"[bold]{report['headline'] or 'Role not inferred'}[/bold]\n\n"
        f"[bright_cyan]Fields[/bright_cyan]  {escape('  |  '.join(pillars))}\n\n"
        f"[bright_cyan]Measurable results[/bright_cyan]\n"
        + "\n".join(f"[green]•[/green] {escape(point)}" for point in proof_points)
        + f"\n\n[dim]Preview: {escape(preview)}[/dim]"
    )
    console.print(Panel(body, title="[bold bright_cyan]Step 2 / Evidence briefing[/bold bright_cyan]", border_style="green"))


def render_overview(skills: list[str], target: str, remote: bool, include_india: bool, report: dict[str, list[str] | str], database: JobStore) -> None:
    pillars = report.get("pillars", [])
    proof_points = report.get("proof_points", [])
    profile = Panel(
        f"[bold]{report['headline'] or 'Role not inferred'}[/bold]\n"
        f"[dim]{escape(target)}[/dim]\n\n"
        f"[bright_cyan]Skills tracked[/bright_cyan]  {len(skills)}\n"
        f"[bright_cyan]Fields[/bright_cyan]  {len(pillars)}\n"
        f"[bright_cyan]Measurable results[/bright_cyan]  {len(proof_points)}",
        title="[bold bright_magenta]Profile[/bold bright_magenta]",
        border_style="bright_magenta",
    )
    radar = Panel(
        f"[bright_cyan]Market[/bright_cyan]  {'India-aware' if include_india else 'Global listings'}\n"
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
    body = "\n".join(f"[bright_cyan]{escape(skill):<18}[/bright_cyan] {count} active-role mentions" for skill, count in pulse)
    console.print(Panel(body, title="[bold bright_magenta]Market pulse[/bold bright_magenta]", border_style="bright_magenta"))


def introduce_candidate() -> tuple[list[str], bool, str, bool, str, dict[str, list[str] | str]]:
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
    except (ValueError, OSError) as error:
        console.print(f"[yellow]I could not read that resume: {error}[/yellow]")
        text = ""
    report = profile_report(text)
    skills = report["skills"]
    if text and skills:
        show_briefing(report, text)
    elif text:
        console.print("[yellow]I read the text but found none of the skills I track. Is this the right document? Add your skills below.[/yellow]")
    else:
        console.print("[yellow]No resume evidence loaded, so the radar will rely on manual skills only.[/yellow]")
    console.print("\n[bold bright_cyan]Step 3 / Calibrate the search[/bold bright_cyan]")
    console.print("What role should I optimize for? Any field works. Examples: Accountant, Data Analyst, Registered Nurse, Software Engineer")
    suggestion = str(report["headline"])
    target = ""
    for _ in range(3):
        target = clean_query(Prompt.ask("Target role", default=suggestion) if suggestion else Prompt.ask("Target role"))
        if target:
            break
        console.print("[yellow]Enter a job title, for example Accountant.[/yellow]")
    if not target:
        raise SystemExit("No target role given. Re-run and enter a job title such as Accountant or Data Analyst.")
    console.print("Where can you work? Example: India, Hyderabad, remote worldwide")
    location = Prompt.ask("Location preference", default="India")
    console.print("What is your level?")
    level = Prompt.ask("Experience level", choices=["student", "junior", "mid", "senior"], default="student")
    console.print("Should I show only remote roles?")
    remote = Confirm.ask("Remote only", default=False)
    all_skills = list(skills)
    for attempt in range(3):
        manual = Prompt.ask("Add any skills the resume missed (comma-separated, any field)", default="")
        added, rejected = clean_skill_list(manual.split(","))
        if rejected:
            console.print(f"[yellow]Ignored: {', '.join(rejected)}[/yellow]")
        all_skills = list(dict.fromkeys(skills + added))
        if all_skills:
            break
        console.print("[yellow]I need at least one skill to match against. Example: microsoft excel, nursing, python, seo[/yellow]")
    if not all_skills:
        raise SystemExit("No skills to match. Re-run with a text-based resume or type a few skills like: microsoft excel, sql, seo.")
    console.print(
        Panel(
            f"[bright_cyan]Target[/bright_cyan]  {escape(target)}\n"
            f"[bright_cyan]Location[/bright_cyan]  {escape(location)}\n"
            f"[bright_cyan]Level[/bright_cyan]  {level}\n"
            f"[bright_cyan]Remote only[/bright_cyan]  {'yes' if remote else 'no'}\n"
            f"[bright_cyan]Tracked skills[/bright_cyan]  {escape(', '.join(all_skills)) or 'none'}",
            title="[bold bright_cyan]Step 4 / Radar settings[/bold bright_cyan]",
            border_style="bright_magenta",
        )
    )
    return all_skills, "india" in location.lower(), target, remote, level, report


def run_search(
    database: JobStore,
    target: str,
    skills: list[str],
    remote: bool,
    level: str,
    include_india: bool,
    live: bool = True,
) -> list[dict]:
    with console.status("[bright_cyan]Searching roles...[/bright_cyan]", spinner="dots"):
        outcome = find_roles(database, target, skills, remote, level, include_india, live)
    for note in outcome.notes:
        console.print(f"[yellow]{note}[/yellow]")
    if outcome.roles_found == 0:
        console.print(
            f"[yellow]No roles found for '{escape(target)}'. That title may not exist in the job feeds. "
            "Try a broader title such as 'analyst', 'manager' or 'engineer'.[/yellow]"
        )
    elif not outcome.matches:
        console.print(
            f"[yellow]Found {outcome.roles_found} roles for '{escape(target)}', but none list a skill that is on your resume. "
            "I only match skills that appear in both.[/yellow]"
        )
    return outcome.matches


def interactive() -> None:
    database = store()
    banner()
    if database.count() == 0:
        refresh(database)
    skills, include_india, target, remote, level, report = introduce_candidate()
    if include_india and not adzuna_configured():
        console.print("[yellow]A note on India: the free sources skew to the US and Europe. Add free Adzuna credentials to pull India-specific roles in any field.[/yellow]")
    matches = run_search(database, target, skills, remote, level, include_india)
    render_overview(skills, target, remote, include_india, report, database)
    if matches:
        job_table(matches, "Radar matches")
        for job in matches[:3]:
            console.print(
                Panel(
                    f"[bright_cyan]{job['match_score']}% fit[/bright_cyan]\n"
                    f"[bold]{escape(job['title'])}[/bold] at {escape(job.get('company_name') or 'Unknown company')}\n"
                    f"[green]Matched[/green]  {escape(', '.join(job['matched_skills']))}\n"
                    f"[yellow]Build next[/yellow]  {escape(', '.join(job['missing_skills']) or 'no gaps detected')}",
                    border_style="green",
                )
            )
    console.print("\n[dim]Use slash commands like /market, /search data analyst, /open 1, /profile, /refresh, or /quit.[/dim]")
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
            matches = run_search(database, target, skills, remote, level, include_india, live=False)
            if matches:
                job_table(matches, "Radar matches")
        elif normalized.split(" ", 1)[0] in {"search", "/search"}:
            query = clean_query(normalized.split(" ", 1)[1]) if " " in normalized else target
            scoped = run_search(database, query, skills, remote, level, include_india)
            if scoped:
                matches = scoped
                job_table(scoped, f"Results for: {query}")
        elif not normalized:
            continue
        elif normalized.split(" ", 1)[0] in {"open", "/open"}:
            index_text = normalized.split(" ", 1)[1].strip() if " " in normalized else ""
            if not index_text.isdigit():
                console.print("[yellow]Use /open 1 or /open 2.[/yellow]")
                continue
            index = int(index_text) - 1
            if index < 0 or index >= len(matches):
                console.print("[yellow]That result number is out of range.[/yellow]")
                continue
            show_job(matches[index])
        else:
            console.print("[dim]Try /market, /profile, /search nurse, /open 1, /refresh, or /quit.[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser(description="RoleRadar resume-to-role matching for any field")
    parser.add_argument("--sync", action="store_true", help="Refresh the local job cache and exit")
    arguments = parser.parse_args()
    try:
        if arguments.sync:
            refresh(store())
            return
        interactive()
    except (KeyboardInterrupt, EOFError):
        console.print("\n[bright_cyan]Exiting.[/bright_cyan]")
    except (sqlite3.Error, OSError) as error:
        console.print(f"[red]Could not open the local job cache in {DATA_PATH}: {error}[/red]")
        sys.exit(1)
