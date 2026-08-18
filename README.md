# RoleRadar

RoleRadar matches a resume to current AI and machine learning roles using only skills that appear in both the resume and the job listing.

It is a small product with two interfaces that share the same matching idea:

- a **terminal app** for guided resume intake, local job caching, and slash-command search
- a **web app** for resume upload, target-role selection, and ranked live listings

A skill is counted as a match only when it is present in the job title, description, requirements, or tags. The score is the share of the candidate’s extracted skills that also appear in the listing.

## Features

- Resume intake from PDF, TXT, Markdown, pasted text, or a public GitHub / Google Drive HTTPS link
- Skill extraction, role positioning, and proof-point detection from resume text
- Target role, seniority, market, and remote-only controls
- Automatic role scan after a successful web upload
- Ranked results with matched skills and tagged gaps
- Local SQLite cache for the terminal app so later sessions can run offline
- Optional India listings through [Adzuna](https://developer.adzuna.com/) when credentials are set

## How matching works

```text
resume
  → extract text (PDF / TXT / Markdown)
  → detect known technical skills
  → query live AI job listings
  → score = matched skills / extracted skills
  → rank and surface gaps from job tags
```

The default live source is the [AI Dev Jobs API](https://aidevboard.com/openapi.yaml). That feed currently skews US-based. RoleRadar does not invent an India filter on top of it. To include India-specific listings, set `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` before refreshing the terminal cache. Credentials are never committed or displayed.

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

Open [http://localhost:3000](http://localhost:3000). Upload a resume to extract skills and scan listings immediately. Change the target role in the sidebar and rescan at any time. Light and dark themes are available.

To deploy on Vercel, import this repository and set the project **Root Directory** to `web`. No API key is required for the default job source.

## Tests

```bash
.venv/bin/pytest

```bash
cd web
npm run lint
npm run build
```

## Project layout

```text
roleradar/     terminal app: intake, matching, SQLite cache
tests/         matching and resume-path tests
web/           Next.js app and API routes
```
