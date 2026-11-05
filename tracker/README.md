# Tracker

A small dashboard for a job search and a learning plan. It reads a few JSON files and writes two views of the same content:

- `index.html`: a desktop dashboard. It works offline, with no CDN and no web fonts.
- `README.md`: plain Markdown for a phone or the GitHub app.

No LLM runs here. The notes on the page come from fixed rules:

- today's one task, picked from the weekly rhythm (anything closing within 3 days goes first)
- deadlines that passed while an application is still open
- applications nobody checked for `stale_days`
- overdue tasks
- learning weeks that ended but were never marked done
- the merge pace needed to reach an open-source goal

Your Pentarch agent keeps the JSON files up to date; `build.py` only turns them into pages.

## Run

Python 3.10+, standard library only.

```sh
python tracker/build.py --init [DIR]                 # config.json, profile.json and data/ from the examples, into DIR (default: this folder)
python tracker/build.py --config tracker/config.json
python tracker/build.py --config tracker/config.example.json --today 2026-11-05   # demo with the example data
```

Flags: `--config FILE`, `--data DIR`, `--out DIR`, `--lang en|tr`, `--today YYYY-MM-DD`. Flags win over the config file.
`scan.py` takes `--config`, `--data`, `--profile FILE` (default: `profile.json` next to the config), `--today` and `--dry-run`; it exits 1 when a board could not be fetched and lists those under `errors` in `scan.json`.
Paths in the config file are relative to that file; paths given as flags are relative to the current folder.

Tests: `python -m pytest tracker -q` (or `python -m unittest discover -s tracker` without pytest). They build the example data on several days, in both languages, into a temp folder.

`data/`, `out/`, `config.json` and `profile.json` are in `.gitignore`, so your own data stays on your machine.

## Profile

`profile.json` (from `profile.example.json`) is for the assistant, not for `build.py`: what roles and seniority to look for, where, what a good posting looks like (`quality`), what rules a posting out (`deal_breakers`), and how to write the CV and cover letter (`cv.language`, `cv.style`, `cover_letter`). Edit it once; every scan, judgement and application follows it. The `cv` block is also what `skills/cv/` reads when it drafts a CV for a posting. Keep the words in Pentarch's `job_boards` filter (titles, exclude, locations) in step with it, since that filter runs before the assistant sees a posting.

## Config

| Key | Type | Default | What it does |
|---|---|---|---|
| `title` | string | `"Tracker"` / `"Takip"` | Page title |
| `lang` | `"en"` or `"tr"` | `"en"` | Label language |
| `data_dir` | path | `"data"` | Folder with the JSON files |
| `out_dir` | path | `"out"` | Where `index.html` and `README.md` go |
| `backlog` | path | `""` | Optional Markdown checklist (see below) |
| `status_log` | path | `""` | Optional log file; the last 8 lines show as "Background jobs" |
| `github_user` | string | `""` | Counts your merged and open PRs on other people's repos via the `gh` CLI. Empty, or no `gh` installed: skipped |
| `important_repos` | list of `"owner/repo"` | `[]` | Merged PRs into these are counted separately |
| `oss_goal` | int | `0` | Merged PR goal (0 = no goal bar) |
| `oss_deadline` | date | `""` | Deadline for the goal |
| `stale_days` | int | `10` | An application not checked for longer gets flagged |
| `followup_days` | int | `14` | A sent application with no answer for longer gets a follow-up note |
| `new_days` | int | `8` | An application added within this many days gets a "new" badge |

## Data files

Every file is optional; a missing file means an empty section. Dates are `YYYY-MM-DD` strings. Records only need the fields they use. Missing fields fall back to the defaults below.

### `applications.json` (list)

| Field | Type | Default | Notes |
|---|---|---|---|
| `id` | string | `""` | Stable key, for the agent |
| `company`, `role`, `location` | string | `""` | |
| `deadline` | date | `""` | Drives the 14-day strip and the deadline notes |
| `deadline_note` | string | `""` | Extra text, e.g. "rolling" |
| `stage` | string | `"watching"` | One of `ready`, `sent`, `process`, `decide`, `watching`, `closed`. Picks the board column |
| `status` | string | `""` | Free text. The card shows the part before the first `:` or `(` |
| `sent_on` | date | `""` | When it was sent (for `sent` / `process`) |
| `cv`, `package` | string | `""` | URL, or a file path relative to `out_dir` (shown only if the file exists) |
| `posting` | URL | `""` | Job posting |
| `priority` | int | `2` | Lower sorts first |
| `note` | string | `""` | |
| `checked` | date | `""` | Last time someone checked the posting |
| `added` | date | `""` | For the "new" badge |

### `learning.json` (list)

Items with a `start` date form the weekly plan; items without one go under "Later".

| Field | Type | Default | Notes |
|---|---|---|---|
| `id`, `name`, `provider`, `link`, `scope`, `done_when` | string | `""` | `done_when` is the "when done" line |
| `order` | int | `0` | Sort order |
| `priority` | string | `""` | Free label, e.g. "core" |
| `week` | string | `""` | Shown as "Week N" |
| `start`, `end` | date | `""` | |
| `status` | string | `""` | `"done"` marks the item finished; anything else is free text |

### `events.json` (list)

| Field | Type | Default | Notes |
|---|---|---|---|
| `id`, `name`, `status`, `link`, `note` | string | `""` | |
| `date`, `date_end`, `register_by` | date | `""` | `register_by` is used for the strip when set |
| `closed` | bool | `false` | Moves it to the past list |

When a task and an event share the same `link`, only the task shows in "Upcoming".

### `tasks.json` (list)

Small things waiting on you.

| Field | Type | Default |
|---|---|---|
| `id`, `task`, `effort`, `link` | string | `""` |
| `due` | date | `""` |
| `done` | bool | `false` |

### `certifications.json` (list)

| Field | Type | Default |
|---|---|---|
| `id`, `name`, `provider`, `cost`, `duration`, `status`, `link` | string | `""` |
| `order` | int | `0` |
| `target` | date | `""` |

### `rhythm.json` (object)

```json
{
  "session": "1 hour, 19:00-20:00",
  "note": "free text",
  "days": ["learning", "algorithms", "learning", "algorithms", "learning", "math", "rest"],
  "practices": {"algorithms": {"label": "algorithms", "name": "Two practice problems", "goal": "...", "link": "https://..."}}
}
```

`days` runs Monday to Sunday. Each entry is `"learning"` (today's task comes from the current learning week), a key from `practices`, or anything else, which counts as a rest day.

### `scan.json` (object, optional)

Output of a job-posting scan. If the file is missing, the Scan section is hidden.

| Field | Type |
|---|---|
| `date` | date |
| `summary` | string |
| `new` | list of `{company, role, link, reason}`; `scan.py` adds `score` (1-5, shown as a pill), `location`, `posted` |
| `changed` | list of `{company, what}` |
| `closed` | list of `{company, reason}` |
| `dropped` | list of `{company, role, reason}` |
| `sources` | list of strings |

### Backlog file (Markdown, optional)

Each `## ` heading with `- [x]` / `- [ ]` lines becomes a progress bar with its next open item. Headings without checkboxes are skipped. Text after ` — ` in a heading is dropped.

## Scanning job boards without a model

`scan.py` reads the public job boards you list in `profile.json`, scores every posting against the profile and writes `scan.json`. It needs no API key and no model: the rules are the profile itself.

```
python tracker/scan.py --config tracker/config.json            # scan, write data/scan.json and data/scan-state.json
python tracker/scan.py --config tracker/config.json --dry-run  # print, write nothing
```

Supported boards (their public JSON endpoints): Greenhouse, Lever, Ashby. Find the slug in a company's careers URL, for example `boards.greenhouse.io/<slug>`, `jobs.lever.co/<slug>`, `jobs.ashbyhq.com/<slug>`, and list it under `boards` in `profile.json`.

How a posting is judged, in order:

1. Title: dropped when it contains an `exclude` word (senior, lead, manager, ...) or none of the `seniority` words (synonyms such as "new grad" and "working student" are built in). An empty `seniority` list skips that check: setup leaves it empty for mid-level and "any level" and only keeps `exclude` (mid-level drops lead/head/principal/staff/director/manager/chief; "any level" drops nothing).
2. Role: a `target_roles` phrase whose every word is in the title ("product designer" in "Junior Product Designer") is a full match; its last word alone ("designer" in "UX Designer") is a weak match; a title with neither is dropped. Seniority words and generic ones (developer, engineer) are ignored here, so "junior unity developer" only needs "unity" and "backend engineer" never matches on "engineer" alone.
3. Location: the board's location text must contain one of `locations` as written (plain substring, no country or city hierarchy: "Canada" does not cover "Toronto, ON"); "remote" also accepts the board's remote flag. An explicit `"exclude": []` drops nothing.
4. Description: dropped on a `signals.deal_breakers` phrase or when every "N+ years of experience" it asks for is above `max_years` (default 2; "2 to 4 years" counts as 2, "founded 10 years ago" is not a requirement).
5. Score 1-5: a full role match (+2) or a weak one (+1), `skills` found in the description (up to +2), a `signals.strong` phrase (+1), a `signals.weak` phrase (-1), posted within 14 days (+1), older than 90 days (-1), a company that rejected you before (-1, read from `applications.json`).

Postings at or above `quality.min_score` go to `new`, sorted by score. A company you already track goes to `changed`, a posting that left the board goes to `closed`, everything else to `dropped` with the reason, so you can tune the profile. `scan-state.json` remembers what was already reported.

Run it from a scheduled task, or let the Pentarch agent run it before its own judgement: the score and reason land in the dashboard either way.

## How the Pentarch agent uses it

The agent never edits the HTML. It edits the JSON files in `data_dir`, then runs `build.py`:

1. Read the file it needs, find the record by `id`, change only the fields that changed, and write the file back as valid JSON (UTF-8).
2. Typical edits:
   - an application was sent: `stage: "sent"`, `sent_on: <today>`, a new `status`
   - a posting was checked: `checked: <today>`
   - a learning week is finished: `status: "done"`
   - a task is done: `done: true`
3. New records get a short unique `id`. Leave unknown fields out instead of writing `null`.
4. A scheduled scan can overwrite `scan.json` as a whole.
5. Run `python tracker/build.py --config tracker/config.json`. Its one-line summary (upcoming count, notes count) is enough to confirm the build.
6. Before a scan, a verdict on a posting or an application, read `profile.json`. Score each posting 1-5 on `quality.scale`, list which `strong`/`weak`/`deal_breakers` lines matched, and apply only when `apply_only_if` holds. CV and cover letter text follow `cv` and `cover_letter` (language, style, length); write the score and the reason into the application's `status`.

`example-data/` shows every field in use, and every section renders from it. `--init` copies it into `data/` with a `SAMPLE` marker file, so the first dashboard shows a notice that the records are samples; delete `data/SAMPLE` once your own records are in.
