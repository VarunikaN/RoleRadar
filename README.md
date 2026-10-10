# RoleRadar

RoleRadar matches a resume to current job listings in **any field** (finance, healthcare, teaching, sales, design, engineering, software and more) using only skills that appear in both the resume and the listing.

Upload a resume, and RoleRadar extracts the skills it can verify on the page, suggests a target role, fetches live listings from several job boards, and ranks them by how much of your skill set each listing mentions. A skill counts as a match only when it appears in the job title, description, requirements, or tags. Jobs that share no skill are not shown.

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

- Resume intake from PDF, TXT, Markdown, or a public GitHub / Google Drive HTTPS link
- A shared vocabulary of 398 skills in 21 fields, with 84 aliases (for example `k8s`, `nodejs`, `powerbi`)
- A suggested role and up to three fields, taken from the categories of the skills found in the resume
- Measurable results: resume sentences that contain a percentage, an amount, or a count, quoted as written
- Target role, seniority, market, and remote-only controls; the target role is pre-filled from the resume
- Ranked results with matched skills, skill gaps (skills the listing asks for that the resume lacks), and the source of each listing
- An "in demand" summary of the most frequently mentioned skills across the retrieved listings
- Light and dark themes

## Job sources

| Source | Coverage | Notes |
| --- | --- | --- |
| [AI Dev Jobs](https://aidevboard.com/openapi.yaml) | Tech, AI and adjacent roles, with skill tags | Server-side text search |
| [Arbeitnow](https://www.arbeitnow.com/api/job-board-api) | Mixed fields, Europe-heavy, many German listings | One feed of about 300 jobs, fetched at most once per hour and filtered locally |
| [The Muse](https://www.themuse.com/developers/api/v2) | Mixed fields, US-heavy | No text search, so the role is mapped to a Muse category and filtered locally |
| [Adzuna](https://developer.adzuna.com/) (optional) | India | Up to 30 listings per search; used when the market is India and `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` are set on the server |

One failing source becomes a warning and the others still answer; RoleRadar reports an error only when every source fails. Each listing shows which source it came from.

## How matching works

```text
resume
  -> extract text (PDF / TXT / Markdown)
  -> detect skills from the shared vocabulary (398 skills, 84 aliases)
  -> query the job sources for the target role
  -> score = matched skills / extracted skills
  -> rank, and list gaps from listing tags and from vocabulary skills found in the listing text
```

Matching is whole-word on both sides, so `sql` does not match `PostgreSQL` or `SQLite`, `git` does not match `GitHub`, and `c++` does not match `c#`. Web addresses inside text are ignored, so `privacy.html` is not read as an HTML skill.

The suggested role comes from the field with the most skills in the resume (for example Finance & accounting suggests Accountant). If no skill is recognised, no role is suggested and you type one.

## Error handling

Bad input is reported, not guessed at:

- An unknown target role reports "No roles found" instead of ranking unrelated jobs.
- Empty, binary, image, scanned, encrypted, oversized, or non-resume files are rejected with a specific reason.
- Resume links must be plain HTTPS addresses on an allowlist of hosts (GitHub and Google Drive). Redirects are re-checked, bodies are capped at 2 MB, and only text is read.
- Skill names you type are validated; single letters and non-skills are ignored and listed back to you.
- A job source that is rate limited, offline, or returning malformed data produces a named warning. Apply links are only kept if they are `http` or `https`.
- Upload, link and job routes are rate limited per client.

## Run locally

Node.js 20 or later.

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000), upload a resume, and change the target role or filters at any time.

India listings are optional. Copy `.env.example` to `.env.local` and fill in free [Adzuna](https://developer.adzuna.com/) credentials. They are read on the server only and are never sent to the browser.

## Deploy

Import the repository into Vercel. No configuration is required for the default job sources. Add `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` as environment variables to enable India listings.

## Tests

```bash
npm test
npm run lint
npm run build
```

`npm test` runs 94 tests with the network replaced by mocks. `npm run lint` is a TypeScript type check.

## Known limitations

- Only skills in the vocabulary are recognised. A skill that is not in it (for example `tally`) is ignored unless you add it as an extra skill.
- Arbeitnow listings are largely German, so English skill terms match only some of them.
- The Muse has no text search, so recall for a role is limited to the first two pages of its mapped categories.
- Coverage of trades and other roles rarely posted on tech-leaning boards is thin; a search for `welder` returns only a few listings.
- An extra skill such as `go` can match unrelated text like "go-to-market".
- The rate limiter and the Arbeitnow cache are in memory, so they apply per server instance.
- There is no labelled evaluation of ranking quality; scores are overlap percentages, not predictions.

## Project layout

```text
app/            Next.js pages and the /api/jobs and /api/resume routes
lib/            skills.json, matching, input guards, job sources
tests/          vitest suites and the shared fixtures in fixtures.json
```
