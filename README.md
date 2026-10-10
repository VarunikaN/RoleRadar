# RoleRadar

RoleRadar matches a resume to current job listings in **any field** (finance, healthcare, teaching, sales, design, engineering, software and more) using only skills that appear in both the resume and the listing.

It is a small product with two interfaces that share the same matching idea:

- a **terminal app** for guided resume intake, local job caching, and slash-command search
- a **web app** for resume upload, target-role selection, and ranked live listings

A skill is counted as a match only when it is present in the job title, description, requirements, or tags. The score is the share of the candidate's extracted skills that also appear in the listing. Jobs that share no skill are not shown.

## AI domain

RoleRadar uses **no machine learning and no LLM**. It is a rule-based information-retrieval and keyword-matching system: a curated skill vocabulary, whole-word matching, and a transparent overlap score.

| Domain | Used here? |
| --- | --- |
| Generative AI (LLMs, text or image generation) | No |
| Agentic AI (autonomous multi-step agents, tool use) | No |
| Machine learning (trained or learned models) | No |
| Rule-based matching / information retrieval | Yes |

Every score can be reproduced by hand from the listing text. The trade-off is that it cannot understand synonyms outside its vocabulary. Natural extensions, none of which are built: semantic matching with embeddings (NLP), resume tailoring with an LLM (generative), and automatic applications (agentic).

## Features

- Resume intake from PDF, TXT, Markdown, pasted text, or a public GitHub / Google Drive HTTPS link
- A shared vocabulary of 398 skills in 21 fields, with 84 aliases (for example `k8s`, `nodejs`, `powerbi`)
- A suggested role and up to three fields, taken from the categories of the skills found in the resume
- Measurable results: resume sentences that contain a percentage, an amount, or a count, quoted as written
- Target role, seniority, market, and remote-only controls
- Ranked results with matched skills and gaps (skills the listing asks for that the resume lacks)
- Local SQLite cache for the terminal app so later sessions can run offline
- Optional India listings through [Adzuna](https://developer.adzuna.com/) when credentials are set

## Job sources

| Source | Coverage | Notes |
| --- | --- | --- |
| [AI Dev Jobs](https://aidevboard.com/openapi.yaml) | Tech, AI and adjacent roles, with skill tags | Server-side text search |
| [Arbeitnow](https://www.arbeitnow.com/api/job-board-api) | Mixed fields, Europe-heavy, many German listings | One feed of about 300 jobs, fetched once per hour and filtered locally |
| [The Muse](https://www.themuse.com/developers/api/v2) | Mixed fields, US-heavy | No text search, so RoleRadar maps the role to a Muse category and filters locally |
| [Adzuna](https://developer.adzuna.com/) (optional) | India | Needs `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` |

One failing source becomes a warning and the others still answer; RoleRadar reports an error only when every source fails. Each listing shows which source it came from.

## Error handling

Bad input is reported, not guessed at:

- An unknown target role reports "No roles found" after a live lookup, instead of ranking unrelated cached jobs.
- Empty, binary, image, scanned, encrypted, oversized, or non-resume files are rejected with a specific reason in both apps.
- Resume links must be HTTPS. The terminal app blocks private and loopback addresses and re-checks every redirect; the web app only fetches an allowlist of hosts and returns text only.
- Skill names you type are validated; single letters and non-skills are ignored and listed back to you.
- A job source that is rate limited, offline, or returning malformed data produces a named warning. The terminal app keeps working from its cache.
- Listing text is escaped before it is printed, so titles such as `[Remote]` cannot break the terminal display. URLs inside text are ignored when matching, so `privacy.html` is not read as an HTML skill.

## How matching works

```text
resume
  -> extract text (PDF / TXT / Markdown)
  -> detect skills from the shared vocabulary (398 skills, 84 aliases)
  -> query the job sources for the target role
  -> score = matched skills / extracted skills
  -> rank, and list gaps from listing tags and from vocabulary skills found in the listing text
```

The suggested role comes from the field with the most skills in the resume (for example Finance & accounting suggests Accountant). If no skill is recognised, no role is suggested and you are asked to type one.

## Known limitations

- Only skills in the vocabulary are recognised. A skill that is not in it (for example `tally`) is ignored unless you type it as an extra skill.
- Arbeitnow listings are largely German, so English skill terms match only some of them.
- The Muse has no text search, so recall for a role is limited to the first two pages of its mapped categories.
- Coverage of trades and other roles that are rarely posted on tech-leaning boards is thin; for example a search for `welder` returns only a few listings.
- A typed skill such as `go` can match unrelated text like "go-to-market".
- The web rate limiter is in memory, so it applies per server instance.
- There is no labelled evaluation of ranking quality; scores are overlap percentages, not predictions.

## Terminal app

Python 3.10+.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/roleradar
```

On first launch, RoleRadar downloads live roles and stores them in `~/.roleradar/roleradar.db`. Refresh the cache without opening the interactive session:

```bash
.venv/bin/roleradar --sync
```

| Command | Action |
| --- | --- |
| `/profile` | Show the extracted profile and current matches |
| `/market` | Show demand signals from cached job tags |
| `/search <query>` | Search a different role focus |
| `/open N` | Inspect listing `N` |
| `/refresh` | Resync live jobs |
| `/quit` | Exit |

## Web app

```bash
cd web
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Upload a resume to extract skills and scan listings immediately; the target role is pre-filled from the resume and can be changed. Change the target role in the sidebar and rescan at any time. Light and dark themes are available.

To deploy on Vercel, import this repository and set the project **Root Directory** to `web`. No API key is required for the default job sources.

Matching is whole-word on both sides, so `sql` does not match `PostgreSQL` or `SQLite`, `git` does not match `GitHub`, and `c++` does not match `c#`. The terminal and web apps read the same `skills.json` and are tested against the same vectors in `tests/parity.json`.

## Tests

```bash
.venv/bin/pytest
```

```bash
cd web
npm test
npm run lint
npm run build
```

## Project layout

```text
roleradar/     terminal app: intake, matching, job sources, SQLite cache, skills.json
tests/         matching, intake, store, job-source tests and parity.json
web/           Next.js app, API routes, lib/ (matching, guards, sources), vitest tests
```
