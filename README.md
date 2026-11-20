<p align="center"><img src="assets/pentarch.png" width="96" alt=""></p>

<h1 align="center">Pentarch</h1>

<p align="center">
A personal assistant that lives on your own computer and talks to you over Telegram.<br>
It runs on the AI agent you already use, remembers what you tell it, works through its own routines all day,<br>
and asks before it does anything you can't take back.
</p>

<p align="center">
<a href="#install">Install</a> ·
<a href="#what-it-does">What it does</a> ·
<a href="#telegram-commands">Commands</a> ·
<a href="#configure">Configure</a> ·
<a href="#safety">Safety</a> ·
<a href="#türkçe">Türkçe</a>
</p>

![Panel](docs/panel-desktop.png)

## Quick start

You need three free tools and a way to talk to it, usually a Telegram account (e-mail, Discord, Slack or Signal work instead): [Python](https://www.python.org/downloads/) 3.10+ (on the installer's first screen, tick the box "Add python.exe to PATH" before you click Install), [Git](https://git-scm.com/downloads), and [Node.js](https://nodejs.org/) if your AI is Claude, Gemini or Codex. You also need an AI account; Google's Gemini login is free. The installer checks for these and tells you where to get anything missing. Use your own computer, not a shared or school one: the keys sit in plain files that any program running as you can read.

Windows: click Start, type PowerShell and open it (a blue window). Copy the line below, right-click inside the window to paste it, press Enter and wait until the text stops moving:

```powershell
irm https://raw.githubusercontent.com/RizgarOzan/pentarch/main/install.ps1 | iex
```

Linux and macOS:

```bash
curl -fsSL https://raw.githubusercontent.com/RizgarOzan/pentarch/main/install.sh | sh
```

It clones the repo into `~/pentarch`, makes a virtualenv and starts the guided setup, which takes 10 to 20 minutes (the Telegram pairing wait, the agent install and its browser login are the slow parts): pick a language, name the assistant, choose the AI you already pay for (or a free Gemini login), paste a Telegram bot token (in Telegram, message @BotFather, send `/newbot` and copy the long token; nothing shows while you paste), then send your bot `/start` followed by the code setup prints. Both scripts are short; read them first ([install.sh](install.sh), [install.ps1](install.ps1)) if you like. Prefer to do it by hand? See [Install](#install).

Pentarch runs on your own computer, so it only answers and runs its routines while that computer is on and awake. A spare laptop, a small home server or an Android phone with Termux works if you want it around the clock.

## Why

Chat apps forget you when the tab closes, and most "agent" projects want a server, a database and a stack of API keys before they say hello. Pentarch is one Python process on your machine. It drives the agent CLI you're already logged in to (Claude Code, Gemini CLI, Codex or OpenCode) or, with no CLI at all, your own model through any OpenAI-compatible endpoint, keeps everything it knows about you in plain markdown files you can open and edit, and reaches you where you already are: Telegram, or e-mail, Discord, Slack or Signal if you'd rather skip Telegram.

A normal day looks like this. At 09:00 it sends a morning brief: what's due, what you're waiting on, one thing it suggests doing first. You send it a voice note from the bus; it transcribes it locally and files the note. A routine notices a job posting that matches your profile and asks with Yes/No buttons whether to add it to your tracker. In the evening it sums up the day. Overnight it tidies its own memory. None of that sent a message, pushed code or deleted a file on your behalf, because outward actions always wait for your yes.

## How it fits together

```
 you ── Telegram ──┐                       ┌── Claude Code / Gemini CLI / Codex / OpenCode
       (or e-mail, │                       │   (the agent does the thinking and the tool use)
        Discord)   ▼                       │
              app/pentarch.py ─────────────┤
              one process: chat, routines, ├── ~/.pentarch       settings, memory, rules, secrets
              reminders, approvals, panel  ├── your notes folder  markdown wiki, searched with FTS5
                       │                   └── optional API       OpenRouter, Groq, Ollama… for cheap one-shot work
                       ▼
           http://127.0.0.1:47824  (local panel)
```

## What it does

### Talk to it
- **Telegram chat** with text, photos, voice notes and buttons. With Claude Code the chat stays in one long-lived session all day, so replies are quick and the prompt cache stays warm. Hard questions move to a deeper model on their own.
- **Other doors (optional).** E-mail (IMAP in, SMTP out), a Discord bot, a Slack bot and Signal (through [signal-cli](https://github.com/AsamK/signal-cli)) go through the same handling as Telegram, and only answer you: the sender address, user id or phone number you set. Off until you turn them on. WhatsApp isn't here because its official API only delivers messages to a public HTTPS webhook, and Pentarch doesn't open a port to the internet.
- **Voice.** Voice notes become text on your machine (faster-whisper). It can answer with voice too (edge-tts, or Piper offline). Filler words are dropped from the transcript. If you set `whisper.groq_key_env` to the name of an env var holding a Groq key, voice goes to Groq's hosted whisper first (faster, but the audio leaves your machine) and falls back to local whisper.
- **Push-to-talk (Windows, off by default).** Hold F9, speak, let go, and the recording goes in like a voice note. Needs ffmpeg and your microphone's name in `push_to_talk.mic`.
- **Meeting assistant.** `python -I app/pentarch.py meeting "title"` opens a local page that transcribes the other side of a call (Meet, Zoom...), suggests questions toward the `meeting.goal` you set, drafts an answer when you're asked something, and saves the transcript and a summary to your notes. Audio never touches the disk. It needs `pip install soundcard numpy faster-whisper`.
- **Panel.** A local page at `http://127.0.0.1:47824` with the chat, health, spending, reminders, the job board, proposals waiting for a yes, and every setting. It works in a phone-sized window too. `python -I app/pentarch.py panel` opens it and prints the link; from another computer, run `ssh -L 47824:127.0.0.1:47824 <this machine>` and open the same link there.

### Remember
- **Memory you can read.** Your profile, a memory page the nightly round keeps tidy, a rules file, and fast full-text search over your notes and past chats. Semantic search through a local Ollama model is optional.
- **Learning loop (opt-in).** With `learning.enabled` on, a cheap model looks at each chat and may propose a memory note or a fix to one of its skills. Nothing is written until you say `approve N`, and a line that looks like an injection is refused.
- **Imports.** `python -I app/pentarch.py import` reads your existing Claude Code, Codex, Hermes and OpenClaw instructions, memory and skills and shows what it would bring over; `--write` brings them over. Hermes scheduled jobs come out as ready `routine add` commands for you to run, never added on their own. Secret files (`.env`, `auth.json`) are never read.

### Work on its own
- **Routines.** Morning brief, evening summary, a heartbeat checklist, reply checks for messages you're waiting on, news in your field, upcoming deadlines found in your notes, a weekly retro of what went wrong, and a weekly look for new tools. Each one can be switched off in the panel. The briefs read your calendar through the agent's calendar tool, or on any CLI from a private iCal link (Google "Secret address in iCal format", Outlook "Publish calendar"): put `PENTARCH_ICAL=<link>` in `secrets/keys.env`; the agent never sees the link.
- **Reminders and tasks.** "Remind me at 10" or "do this tonight" become entries that fire on time. A task runs in its own agent session, under a daily budget cap.
- **Responsibilities.** A standing goal the assistant owns, like "keep my applications list current" or "watch this repo until CI is green". It wakes on a timer or when a command's output changes, keeps its own notes file, picks its next wake-up, and stays quiet while it works. It only writes to you when the goal is done, when a decision is yours, or for urgent news. Each responsibility has its own rules: allowed, ask first, never.
  `python -I app/pentarch.py responsibility add <name> "goal" her=240`
- **Your own routines.** Anything you want on a clock with no end goal, like "every Monday at 9 summarise my open PRs". It runs on the fast model and is told to stay read-only; anything that needs a change comes back as a proposal. Under Claude Code a hook blocks known write commands, Gemini runs it in its ask-first mode and Codex in its read-only sandbox; on OpenCode the read-only part is an instruction only. A routine asked for in chat is set up only after you press Yes. You can also add one yourself:
  `python -I app/pentarch.py routine add prs mon@09:00 "summarise my open PRs"` (also `08:30` for every day, `1,15@09:00` for those days of the month, `"20@09:00 jan,apr,jul,oct"` for only those months (a quarterly tax date), `90m` for every 90 minutes from 09:00 to 23:00, or `90m@07:00-01:00` for your own window, `09:00,21:00` for twice a day; `routine list | pause | resume | remove <name>`). For a plain reminder with no AI run, like pills: `python -I app/pentarch.py routine remind pills 09:00,21:00 "take your pills"`. If the computer was asleep it still goes out within 2 hours and says how late it is; later than that it is skipped, so keep a phone alarm for anything that matters
- **Quick answers.** One word that shows your numbers at once, with no AI run, so it costs nothing and answers in under a second. In the chat: `shortcut add morning = receivables + shifts`, then send just `morning`. The readers are `receivables`, `shifts`, `study`, `expenses`, `routines` and `nudges` (a polite payment reminder for each overdue line owed to you, ready to copy; Pentarch sends nothing itself); they only read your own files. `shortcut list` and `shortcut remove <name>` manage them. Names that already mean something (`help`, `stop`, `yes`...) are refused.
- **Proposals.** When a routine finds work that would help, it suggests it with Yes/No buttons. Proposals never run before your yes (see Safety for what guards the agent itself).
- **Expenses.** `expense add flour 1200` (quotes for a two-word name) writes a dated line into `expenses.md` in your notes; `expenses` answers with this month's total, the biggest names and last month, no AI run. Unreadable lines are reported, not silently dropped.
- **Interview prep.** The `interview` skill keeps a story bank, shows which themes still have no story, matches a story to a question and checks structure (a number in the result, "I" not "we", under about 90 seconds). `apply.py stats` shows your funnel and the applications that went quiet.
- **Recruiter replies.** When the mail check is on and a mail names a company you applied to (stage `sent` or `process`) and reads like a rejection, an interview invite or an offer, you get a Yes/No: "mark Acme closed / in process / decide in the tracker?". It is matched by code, the question is built from your own tracker, and nothing moves before your yes.
- **Notes to running jobs.** Write a follow-up while a long job runs and it is added to that job. Under Claude Code the job reads it after its next tool call; other CLIs get it when they finish. A finished task can also queue its own next step when that step needs no decision from you and sends nothing outward.

### Think it over
- **Council (`council: question`).** Several models get the same question at once. They answer, read each other's answers, argue a second round and vote. Seats can be any agent CLI or any OpenAI-compatible API, and each seat can take a different angle (tester, HR, security…).
- **Konsey (`/konsey idea`, Claude Code).** Four advisors (Advocate, Skeptic, Employer, Builder) each review one idea on their own, and a judge returns BUILD, FIX FIRST or KILL with the biggest risk and a 10-minute test. Verdicts are logged in your notes. See [skills](skills/README.md).
- **Debate (`debate: topic`).** Every council seat writes ideas, they critique each other twice, vote and score, and the deep model picks one. Takes 10-40 minutes.
- **Helpers.** With Claude as the lead you can add Gemini or Codex as helpers. When a job splits, up to 8 subtasks run side by side on the helpers and Claude checks each answer before using it. [Details below](#claude-leads-helpers-widen).

### Career
- Watches open hackathons and junior jobs: Devpost, the Remotive, Arbeitnow and RemoteOK feeds, and the Greenhouse, Lever, Ashby, Workable, Recruitee, SmartRecruiters and Personio boards you pick. Postings that rule out visa sponsorship or need a clearance are flagged.
- Tracks your GitHub pull requests.
- A small offline dashboard for applications and a learning plan, which runs without any model ([`tracker/`](tracker/README.md)).
- LinkedIn and CV skills that draft posts, score your profile and check a CV against a posting. They never log in or post for you.
- Each morning, application packages for up to four of the best new postings, built at once: CV, cover letter, a short e-mail and a LinkedIn note. CVs come from your profile and measured GitHub facts, a second model scores each one against the posting out of 100 and a weak one gets revised. With only one agent CLI the same model writes and scores, and the message says so; list a second one under `agent.workers` for an independent score. Under Claude Code, postings are read with every tool switched off, so text hidden in one can change a draft but never act. Gemini and Codex keep their read-only tools there. Applying and e-mailing reach you as Yes/No buttons. The `apply` skill fills the form, checks every value against your profile and sends only after you say yes to that one application.

### For a shop or freelancer
Detailed setup asks once whether you want this (quick setup skips it; re-run `python -I setup.py` and say no to quick). Say yes and it saves your calendar link and drops starter `shifts.md` and `receivables.md` files in the notes folder. Then, from Telegram: "who is on Saturday?" (reads `shifts.md`), "who owes me money?" (reads `receivables.md`); "Mia paid" or "add 500 from Mia due Dec 1" edits the file through `receivables ekle` / `receivables odendi`, "what's on my calendar tomorrow?". The numbers are counted from the files, not guessed by the model. The morning brief and reminders only fire while the PC is on, so keep it awake at that hour or run Pentarch in Docker on an always-on machine.

Adding a client call or deadline needs no calendar login either: "put the dentist on Dec 5 at 14:30" makes the agent run `event 2026-12-05 14:30 "Dentist"`, which sends an `.ics` file to your Telegram. Tap it and Google, Apple or Outlook calendar adds it. Pentarch never writes to a calendar itself.

### For students
Write `date | course | what` lines in `study.md` in the notes folder (`2026-12-05 | Calculus | midterm exam`; `- [x]` when done). `study` lists what is late, due this week and exams in the next 30 days, and at 08:00 you get the same list when there is something. Link your timetable as a calendar (Google Calendar can subscribe to most university timetables) and the morning brief shows classes too.


### Extras, off by default
- **Windows notifications** from apps you choose, with a cheap model filtering out the noise.
- **Desktop control** (screenshot, click, type) for the agent, with no extra packages.
- **Sandbox.** With `sandbox.backend: docker` the agent is told to run outside code (a cloned repo, a downloaded script) through `app/kum.py`, in a throwaway container that sees only the current folder and has no network. Under `acceptEdits` that is the only shell it gets beyond Pentarch's own scripts. With the default local backend `kum.py` refuses to run anything, so it can't be used as a way around the rules. Under `bypassPermissions` it is a rule the agent follows, not a fence. With `sandbox.backend: ssh` and `sandbox.host` (a host from your `~/.ssh/config`, key login, no password prompt) the same commands run on that machine in `sandbox.dir` (default `~/pentarch-work`); files are not copied over, so the agent clones or downloads there.
- **Data quota mode.** On a metered connection it spreads the monthly cap over the days left and holds heavy jobs back.
- **Tiered routing (`routing.enabled`).** Ledger jobs start on a cheap model and move up to a stronger one only when a review says the answer isn't good enough. `python -I app/pentarch.py routing` shows the last week.
- **Nightly self-improvement (`self_improve.enabled`).** At 03:50 it looks over the day's errors and proposes fixes as Yes/No. Code changes are only ever written as a `.patch` file for you to apply.
- **Shadow mode.** The shorten and triage jobs also run on a second endpoint (`shadow.base_url`) and both answers are logged, so you can see whether a cheaper model would do. You only ever get the main answer.

## Install

You need Windows 10/11, Linux, macOS or an Android phone (see below), Python 3.10+, [Node.js](https://nodejs.org/) (npm installs the agent CLI), [git](https://git-scm.com/downloads) and a Telegram account, or one of the other doors (e-mail, Discord, Slack, Signal) set up in full setup instead. If the agent CLI isn't installed or logged in yet, setup offers to do both.

| | Windows | Linux / macOS | Android (Termux) |
|---|---|---|---|
| Chat, memory, routines, council, career tracker, panel | yes | yes | yes |
| Starts by itself | startup shortcut | systemd user service / launchd agent | Termux:Boot |
| Push-to-talk (F9), desktop control, Windows notification reading, `net.py` | yes | no | no |

The Linux and macOS path is newer and has had less use than Windows. CI runs the tests on all three systems; if something breaks on yours, please open an issue.

| Agent CLI | What you get |
|---|---|
| Claude Code | every feature, including the budget and safety hooks and the one-session-all-day chat |
| Gemini CLI | the chat in one session per day; free quota with a Google login |
| Codex | the chat in one session per day; uses your ChatGPT account |
| OpenCode | the chat in one session per day; runs on your own key, including OpenRouter's free models |

On the three non-Claude CLIs there are no budget caps or safety hooks, and the agent's own sandbox may stop it from writing into `~/.pentarch`. Reminders and routines you ask for in chat still get saved: the agent writes a `REMIND:` or `ROUTINE:` line and Pentarch stores it and tells you what it stored. Pentarch has no general "send this e-mail" action; outgoing mail is limited to job applications and follow-ups, each sent only after your Yes.

```bash
git clone https://github.com/RizgarOzan/pentarch.git
cd pentarch
python -m venv .venv
.venv\Scripts\python setup.py      # Linux/macOS: .venv/bin/python setup.py
```

Calling the venv's Python by its path skips `activate`, which PowerShell blocks on many Windows machines.

Setup talks you through it in English or Turkish, shows "Step 3/6" as it goes, and checks each piece. It first says whether Python, git and npm are there and where to get whatever is missing.

**Quick setup** is the default. It asks the questions below and takes the default for everything else:

1. **The basics:** your name and the assistant's name.
2. **The agent**, the program the assistant runs to think. Not sure? Claude if you pay for Claude, otherwise Gemini (free with a Google account). If it isn't installed, setup offers to run the `npm i -g` line for you. Then it sends a one-word test; if the login is missing it tells you what to type, can open a login window, and tests again when you're done. With Claude it also asks your plan.
3. **Telegram:** make a bot with @BotFather (`/newbot`) and paste the token. Easiest is to open web.telegram.org on the computer and copy it from there.
4. **Free keys:** OpenRouter and Groq (free tiers), then NVIDIA (trial credits that run out), one at a time. In quick setup the default answer is no; say yes and it opens that service's key page in your browser (NVIDIA's is on build.nvidia.com) and walks you through it. They're optional: the assistant hands them cheap jobs and they sit on the council.
5. **Installing:** one yes/no on whether you're looking for a job or internship (yes asks the career questions below; pick `intern` for internships only, and a place in Turkey offers Turkish company boards), and one on whether the assistant may read your inbox (Gmail needs an app password; it walks you through it). The shop and freelancer questions below are in detailed setup only.
6. **A few yes/no's with defaults:** one sentence about what you do, nightly auto-update, a starter wiki folder, and whether to download the 300 MB voice package (say no on a slow or metered line). On Windows it also adds a startup shortcut and a desktop shortcut and tells you so; with Claude it copies the bundled skills and sub-agents into `~/.claude`.
7. **Pairing and start:** it opens a `t.me` link to your bot. Press Start in Telegram, setup sees it and the bot says hello. Then it offers to start the assistant in the background.

**Detailed setup** (answer "no" to the first question) also asks for the notes folder, the three models, the permission mode, another API (Ollama, LM Studio or your own URL), council seats, career filters, MCP servers (handed to whichever agent CLI you picked: Claude Code, Gemini CLI, Codex or OpenCode), the routines and the shortcuts. `insa` (nightly self-build) and `posta` (mail check) start off either way. You can run setup again any time; it keeps what you already set. If you stop halfway, start over: it doesn't resume, but once a run has finished its answers come back as the defaults.

**Getting the keys.** For every key it asks for, setup says what the service is, whether you need it and whether it has a free tier, prints the sign-up and key pages, offers to open the page in your browser, and lists the steps. When you paste the key it checks the format, then makes one free call to see the service takes it. If it doesn't, it says why and lets you paste again. Press Enter on an empty prompt to skip an optional key; run setup again later to add it.

| Service | What for | Needed? | Free tier | Sign up | Key page |
|---|---|---|---|---|---|
| Telegram | the bot you chat with | yes, to chat over Telegram | free | [telegram.org/apps](https://telegram.org/apps) | [@BotFather](https://t.me/BotFather), send `/newbot` |
| OpenRouter | cheap jobs, council seats | optional | `:free` models, 20 a minute and 50 a day | [openrouter.ai](https://openrouter.ai/) | [openrouter.ai/keys](https://openrouter.ai/keys) |
| Groq | cheap jobs, voice notes | optional | free plan | [console.groq.com](https://console.groq.com/) | [console.groq.com/keys](https://console.groq.com/keys) |
| NVIDIA | cheap jobs, council seats | optional | trial credits | [build.nvidia.com](https://build.nvidia.com/) | [API keys](https://build.nvidia.com/settings/api-keys) |
| Anthropic | Claude on pay as you go (`plan = api`) | only for `plan = api` | none, you add credit | [platform.claude.com](https://platform.claude.com/) | [settings/keys](https://platform.claude.com/settings/keys) |
| Ollama, LM Studio | models on your own computer | optional | free, no key | [ollama.com/download](https://ollama.com/download), [lmstudio.ai](https://lmstudio.ai/) | none |

The same guide runs when you add a council seat with `python -I app/koltuk.py add`. NVIDIA's key isn't test-called, because its model list is public and a chat call would spend credit.

Settings, memory and keys go to `~/.pentarch`. Only the job tracker's own files (`tracker/config.json`, `profile.json`, `data/`, all gitignored) stay in the clone. Setup adds a startup shortcut that uses the Python you ran it with, so run it from the venv. It offers to install `requirements.txt`; about 300 MB of that is the optional local voice stack.

**First run.** If you didn't let setup start it, copy the line setup printed after "Start it with" and run it. It uses the venv's Python by its full path, so it works from any folder. By hand it is:

```bash
.venv\Scripts\python -I app/pentarch.py      # Linux/macOS: .venv/bin/python -I app/pentarch.py
```

If you skipped the pairing, send your bot `/start <code>` with the code setup showed you. It is also in `~/.pentarch/secrets/telegram-pair.txt`, and the console reminds you while there is no owner. The chat that sends the right code becomes the owner; everyone else is ignored.

**Checking and updating.** `python -I app/pentarch.py doctor` checks the config, the notes folder, the agent CLI, ffmpeg, the Telegram token, every key the config names (by name only; it never prints a value) and the two ports, and marks each line `OK`, `--` (skipped) or `!!` (fix this); with any `!!` it ends by telling you to fix them and run it again. It also checks the internet, and on Windows it looks for app crashes in the last day, nearly full drives and VPN adapters. `python -I app/pentarch.py update` runs `git pull --ff-only`, but only when the clone has no local changes; a running Pentarch restarts itself when the code changes. `python -I app/pentarch.py backup [file.zip]` zips notes, memory, routines and config into one file; the `secrets/` folder with your keys is left out.

**Auto-update.** The `guncelle` routine, off by default (turn it on in setup or the panel), does that same update every night at 05:10 and sends you the list of what changed when a new version came in. After the restart Pentarch installs any new or changed skills by itself (`python -I setup.py --upgrade`); a skill you edited yourself is left alone. New numbered rules from the template are added to your `kurallar.md` (the old file is kept as `kurallar.md.bak`); your own rules stay as they are. Files you added to the folder don't block the update. If tracked files have local changes it skips the pull and only logs it, so your edits are never overwritten. To turn it off, answer "no" to the auto-update question in `python -I setup.py`, or add `guncelle` under Settings > Disabled routines in the panel.

**Updating an older install.** Installs from before auto-update existed need one manual update; after that the nightly routine takes over. If you use an AI coding agent (Claude Code, Codex, Cursor and so on), open it in your Pentarch folder and paste this:

```text
This folder is my Pentarch install. Run `git status`. If there are local changes, list them and ask me what to do before touching anything. If it is clean, run `git pull --ff-only`, tell me in a few lines what changed (`git log --oneline` from the old commit to the new one), then run `python -I setup.py` and walk me through any new questions. Don't delete or reset anything.
```

Without an agent, in the Pentarch folder: `git pull --ff-only`, then `python -I setup.py`.

### On an Android phone, no computer

The phone can run it. Install Termux and Termux:Boot from F-Droid (the Play Store build is outdated), then in Termux:

```bash
pkg install python nodejs git ripgrep procps
termux-setup-storage
npm i -g @google/gemini-cli --ignore-scripts
gemini
git clone https://github.com/RizgarOzan/pentarch.git && cd pentarch && python setup.py
```

- `--ignore-scripts` skips a native build that fails on Termux. If Gemini's search later says `spawn rg ENOENT`, link Termux's ripgrep over the bundled one.
- Log in to `gemini` with a Google account, not an API key: the login gives about 1,000 requests a day and 60 a minute; a free key gives 250 a day.
- Setup notices Termux, puts the wiki in `Documents/wiki` so Obsidian on the same phone can open it, and offers a boot script that starts Pentarch with the phone and restarts it 30 seconds after it dies.
- Keep Android from killing it at night: take Termux out of battery optimisation (Settings > Apps > Termux > Battery > Unrestricted). On Android 14+ also turn on Developer options > "Disable child process restrictions"; Android 12-13 need an adb command for the same thing. Open the Termux:Boot app once, or it never runs the boot script.
- No wiki yet? Setup creates an empty one and can back its history up to a private GitHub repo you make first.

iPhone can't do this: iOS doesn't let an app keep a server running. Use an old Android phone or any always-on computer. I tested this path on Windows with the Windows-only parts switched off, not on a real phone yet.

### In Docker, on a server or NAS

```bash
git clone https://github.com/RizgarOzan/pentarch.git && cd pentarch
mkdir -p pentarch-data notes                    # make them yourself, or Docker creates them owned by root
# the container runs as uid 1000; on a host where you are someone else: sudo chown -R 1000:1000 pentarch-data notes
docker compose run --rm pentarch python setup.py   # answer first; start it only after this
docker compose up -d
docker compose exec pentarch python -I app/pentarch.py panel   # prints the panel link
```

- The image bakes in Claude Code by default. `PENTARCH_AGENT_CLI=gemini` (or `codex`, `opencode`, `none`) before `docker compose build` picks another; `none` is for `agent.cli` `api` with your own key or a local model. `PENTARCH_VOICE=false` leaves out voice and makes the image a lot smaller.
- Log the CLI in once with `docker compose run --rm pentarch claude` (or `gemini`). The login lives in the `home` volume and survives rebuilds.
- Copy `.env.example` to `.env` and set `TZ` to your timezone (the default is UTC, so the 08:30 routines would run at the wrong hour).
- Update: `git pull && docker compose build && docker compose up -d`. Setup is not needed again unless the release notes say so.
- Config, keys and memory are in `./pentarch-data`; notes in `./notes`, or point `PENTARCH_NOTES` at an existing folder. Back up `pentarch-data`. The career tracker's board and application records live in the `home` volume (`tracker-state`), not there.
- The panel is published on the host's `127.0.0.1:47824` only. To reach it from another machine, use an SSH tunnel or Tailscale, not a public port.
- Ollama or LM Studio on the same host: use `http://host.docker.internal:11434/v1` as the base URL.
- Things that need a desktop don't work in the container: the Windows-only parts, opening the panel in a browser for you, and the `docker` sandbox for `kum` (the container already keeps it off your host; use `ssh` for a separate box).
- I haven't built this image myself yet; the files are checked by the test suite, not by a real `docker build`.

### Claude leads, helpers widen

Set `agent.cli` to `claude` and list helper CLIs in `agent.workers`, for example `["gemini", "codex"]`. Claude stays the one you talk to and the one that decides. When a job splits, it runs `alt.py` with up to `agent.max_parallel` subtasks (8 by default) spread over the helpers, and checks each answer before it uses it. A helper that fails has its task redone on Claude.

Tasks can start with a ready role: `arastirmaci:` (researcher), `okuyucu:` (reader), `hata_avcisi:` (bug hunter), `testci:`, `elestirmen:` (critic), `yazar:` (writer), `ozetci:` (summariser), `wiki:`, `veri:` and more. `python -I app/alt.py --roller` lists them all. Roles that need judgement (`kodcu`, `guvenlik`, `dogrulayici`, `planlayici`) always stay on Claude.

**Other languages.** Setup, the panel and the fixed bot messages come in English or Turkish. At the first setup question pick `3` and type a language (`Deutsch`, `Español`, `Français`...): the assistant then writes to you in it, the CV and cover letter default to it (German, Spanish) and voice replies use a matching voice. Typed commands such as `help` and `cancel` stay English and Turkish; `hilfe`, `ayuda` and `aide` also open the help.

## Uninstall
Pentarch keeps everything in two places: the folder you cloned and `~/.pentarch` (settings, keys, ledger; the notes folder is separate and yours). To remove it:
1. Stop it, then delete the startup entry: Windows `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Pentarch.lnk` and the desktop shortcut; Linux `systemctl --user disable --now pentarch` and delete `~/.config/systemd/user/pentarch.service`; macOS `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.pentarch.plist` and delete that file.
2. Delete the cloned folder and `~/.pentarch`. Docker: `docker compose down -v`.
3. Revoke the keys you gave it (bot token in @BotFather, mail app password, API keys). Deleting the files does not revoke them.
The installer's own installs (Python, Git, Node, the agent CLI) are ordinary programs; remove them the usual way if nothing else needs them.

## Telegram commands

Plain chat covers most things: "remind me tomorrow at 10", "what did I say about X last week", "add a seat to the council". These words skip the model and work instantly:

| Send | What happens |
|---|---|
| `cancel` | stops the current run |
| `pause 2h` / `resume` | pauses automatic messages |
| `council: question` | convenes the council |
| `key: NAME_KEY=value` | stores an API key (name ends in `_KEY` or `_TOKEN`) in `secrets/keys.env` and deletes your message; it is never logged or shown to a model |
| `learn` / `approve N` / `reject N` | proposals from the learning loop |
| `/add note` | drops a note in the wiki's `raw/telefon/`; the nightly round files it into a page |
| `/ask question` | answers from your wiki only and names the pages it used |
| `/status` | the last wiki health scan |
| `internet` / `internet free` / `internet limited` | quota mode status and switch |
| `/test` | runs the end-to-end tests |

Turkish works too: `iptal`, `durdur 2 saat`, `konsey: soru`, `/ekle`, `/sor`, `/durum`, `anahtar:`.

From a shell (the agent uses these as well). `python` here is the venv's Python: activate the venv first, or write `.venv/bin/python` (`.venv\Scripts\python` on Windows). A command that fails exits with code 1, so scripts can check it.

```bash
python -I app/pentarch.py remind "2026-12-01 10:00" "text"
python -I app/pentarch.py task now "job"
python -I app/pentarch.py wait "where" "what"
python -I app/pentarch.py search "word"
python -I app/pentarch.py responsibility list
python -I app/kisi.py goster "name"   # what was already asked or told to someone, so a new session doesn't ask again
python -I app/yasak.py "text"         # exits 1 if it touches a topic or person you ruled out in memory.md
python -I app/denetim.py 7            # what the reply check flagged in the last 7 days
```

## Configure

`~/.pentarch/pentarch.json` holds the settings. Anything you leave out falls back to the defaults in [`app/config.py`](app/config.py), and the panel's Settings page edits the same file. Running `python setup.py` again is safe and keeps your memory files. The keys you'll most likely touch:

| Key | What it does |
|---|---|
| `agent.cli`, `fast_model`, `deep_model`, `light_model` | which agent and which models do the work |
| `agent.workers`, `agent.max_parallel` | helper CLIs and how many subtasks run at once |
| `agent.permission_mode` | `acceptEdits` (safer) or `bypassPermissions` (most routines need it) |
| `plan` | `pro`, `max` or `api`. `pro` keeps scheduled work small so your Claude Pro limit lasts (see Using with Pro) |
| `chat_api` | any OpenAI-compatible endpoint for cheap one-shot work. The key comes from the env var named in `key_env` or from `secrets/keys.env` |
| `council` | the council's seats. Add one with `python -I app/koltuk.py add NAME --preset NAME` (presets: `openrouter`, `groq`, `nvidia`, `freellmapi`, `ollama`, `lmstudio`, or `--agent`), or just ask the bot. `"model": "a,b"` falls back to `b` when `a` is rate-limited |
| `gateways` | e-mail, Discord, Slack and Signal doors; Slack and Discord answer only `owner_id`, Signal only `owner`; e-mail only reads senders in `allowed_from` whose mail passed DMARC or DKIM for exactly their domain at your own server (known for Gmail and Yandex; for others set `auth_server` to the name the Authentication-Results header starts with, or nothing is read), and leaves the rest of your inbox unread |
| `sandbox` | `{"backend": "docker", "network": false}`: the agent runs outside code through `app/kum.py` in a container (a fence under `acceptEdits` only). `{"backend": "ssh", "host": "box", "dir": "~/pentarch-work"}` runs them on another machine instead |
| `jobs_off` | routines that start switched off |
| `opportunities`, `job_boards` | filters for the hackathon and job watch (see the top of `app/firsat.py` and `app/kariyer.py`) |
| `github_user` | turns on PR tracking (needs `gh`) |
| `notify_apps` | Windows notification app id → label, e.g. `{"com.squirrel.Teams.Teams": "Teams"}` |
| `net_quota_gb` | monthly data cap; 0 turns quota mode off |
| `desktop_control`, `voice_replies`, `auto_reply` | switches for the riskier extras |
| `chat_daily_usd` | daily cap on chat spending; once it's reached, chat stops handing work to subagents. 0 means no cap |
| `audit` | the reply check (on by default, see Safety) |
| `shadow`, `push_to_talk`, `meeting` | the extras above |

### Turning on Slack, Signal or Discord

Full setup (`python setup.py`, not quick mode) asks about each one and saves the token for you. To do it by hand, add the block to `~/.pentarch/pentarch.json` and restart Pentarch. Save a token with `python -I app/koltuk.py key PENTARCH_SLACK_TOKEN` (hidden input, goes to `secrets/keys.env`), or send `key: PENTARCH_SLACK_TOKEN=xoxb-…` to the bot on Telegram, which deletes the message.

```json
"gateways": {
  "slack":   {"enabled": true, "channel_id": "C0123ABCD", "owner_id": "U0123ABCD"},
  "discord": {"enabled": true, "channel_id": "123456789012345678", "owner_id": "123456789012345678"},
  "signal":  {"enabled": true, "account": "+905551112233", "owner": "+905551112233"}
}
```

- **Slack:** make an app at api.slack.com/apps, give the bot `chat:write` plus `channels:history` (public channel), `groups:history` (private channel) or `im:history` (a DM), install it, and use the `xoxb-` bot token. Invite the bot to the channel (`/invite @name`). For a DM, turn on the Messages tab under App Home, and use the DM's id (starts with `D`) as `channel_id`. `owner_id` is your member id (profile → ⋯ → Copy member ID). Slack lets apps outside its Marketplace read a channel once a minute, so replies take up to a minute. Add `files:read` and files you send are saved to `~/.pentarch/gelen` for the agent to read. A reply inside a thread is read only if you tick "Also send to channel"; the answer goes back into that thread.
- **Discord:** a bot from discord.com/developers with Message Content intent on, token saved as `PENTARCH_DISCORD_TOKEN`; ids come from Developer Mode → right click → Copy ID.
- **Signal:** install [signal-cli](https://github.com/AsamK/signal-cli) and register or link a number to it. `account` is that number, `owner` is yours. If they're the same (signal-cli linked to your own phone), write to yourself in Note to Self and the reply comes back there. Group messages are ignored. Attachments are copied to `~/.pentarch/gelen`.
- The first poll only marks where the channel is; messages sent before Pentarch started are not answered. If a reply fails to send (network down, Slack hiccup), it's kept and sent before anything new is read; the question isn't asked to the model twice.

The prompts are plain markdown in `~/.pentarch`, and they're yours to edit:

| File | Holds |
|---|---|
| `profile.md` | who you are, your goals, what it may do without asking |
| `kurallar.md` | your rules (the name means "rules") |
| `memory.md` | what it has learned; tidied every night |
| `HEARTBEAT.md` | the checklist the heartbeat routine walks through |
| `wishlist.md` | things you'd like it to learn to do |

## Using with Pro

On a Pro or Max plan, Claude Code draws from the same usage limits as claude.ai and Claude Desktop: one window that resets every 5 hours and one weekly cap. You can see both under Settings > Usage, or with `/usage` in Claude Code. Max gives 5 or 20 times what Pro does. If `ANTHROPIC_API_KEY` is set in your environment, Claude Code bills the API instead of your plan. Pentarch's routines run in the background all day, so on Pro they can eat into the budget you wanted for your own chats.

`setup.py` asks which plan you're on. With `"plan": "pro"`:

- Scheduled runs start lean. They skip your user settings, CLAUDE.md, plugins and skills, and only load the built-in tools they use. Connector tools stay deferred behind ToolSearch. The read-only hook still applies.
- The heartbeat and the other interval routines run half as often. The fixed-time ones (morning, evening, memory, board, update) keep their times.
- The nightly wiki round runs on the light model, and discovery starts switched off. You can turn it on from the panel.
- Daily caps drop to $2 for routines and $8 for tasks, plus one initiative a day. These are the API-equivalent figures from claude's own cost report, used as a gauge. You aren't billed for them.
- The chat starts a fresh session sooner, at about 60k tokens of context, because every turn re-reads the whole context.
- When claude reports that the limit is reached, Pentarch pauses routines and tasks until the reset time it reads from the error and sends you one message about it.

Here is what I measured on 2026-11-15, running the real routine prompts through the same code path, with tokens per run including cache reads:

| Routine | `max` | `pro` | Output |
|---|---|---|---|
| heartbeat | 224k | 41-44k | same (`-`, nothing to report) |
| morning | 174k | 72k | same structure, a real item picked |
| evening | 168k | 63k | same structure |
| wiki round | 368k | 127k | same notes filed and the same question asked |

An empty run went from 54-59k tokens to about 10k. Leaving ToolSearch out made it worse: every connector schema loaded and one empty turn cost 186k. I also tried the heartbeat on haiku and dropped it, because one of two runs sent a "nothing new" message where sonnet stays quiet.

Sources: [Claude Code with Pro or Max](https://support.claude.com/en/articles/11145838-use-claude-code-with-your-pro-or-max-plan), [usage limits](https://support.claude.com/en/articles/11647753-how-do-usage-and-length-limits-work), [Max plan](https://support.claude.com/en/articles/11049741-what-is-the-max-plan), [pricing](https://claude.com/pricing), [model config](https://code.claude.com/docs/en/model-config), [costs](https://code.claude.com/docs/en/costs).

## Skills and agents

[`skills/`](skills/README.md) holds instructions the assistant follows for one kind of task, and [`agents/`](agents) the Claude Code subagents some of them use.

| Skill | For |
|---|---|
| `konsey` | a structured verdict on one idea from four advisors and a judge |
| `ogret` | learning mode: you guess first, it explains, you write a small piece |
| `linkedin-post`, `linkedin-profile`, `linkedin-network`, `linkedin-analyze` | drafting posts, scoring the profile, outreach around your applications, and reading your own numbers |
| `cv` | a one-page CV for a posting, checked against rules |
| `apply` | filling an application form, checking it against your profile and sending it after your yes |

Setup writes a pointer for each skill into `~/.pentarch/beceriler`, so memory search attaches the right one when a request matches. With Claude Code it also copies them into `~/.claude/skills` and `~/.claude/agents`, so they work in any Claude Code session. It never overwrites a skill or agent you already have under the same name.

## Safety

- The agent is told to ask before sending, posting, pushing or deleting, and routines ask through Yes buttons. Mail and job applications go out only through those buttons. Under Claude Code, scheduled runs also get a hook (`app/salt_okunur.py`) that blocks mail sending, calendar, Drive and Notion writes, `git push`/`commit` and `gh` writes. It is a blocklist, not a sandbox: it does not stop `rm` or a raw HTTP request, and Gemini, Codex and OpenCode get no hook. For hard isolation keep `acceptEdits` and turn on the Docker sandbox, or run Pentarch itself in a VM or container.
- Keys live in `~/.pentarch/secrets` and never go into prompts, logs or the repo. Before text goes to an API model (`chat_api` or an `openai` council seat), the values in `keys.env` and common key shapes (OpenAI/OpenRouter `sk-`, Groq, NVIDIA, GitHub, Google, AWS, Slack, Telegram bot tokens) are replaced with `[secret]`. The agent CLI gets your text as it is.
- Helper models count as untrusted unless marked `"trusted": true`: e-mails, phone numbers and card numbers are masked before they see text, and your profile and CV stay away from them. Ollama and LM Studio set up through setup or `koltuk.py` are marked trusted, because they run on your machine. A provider is never trusted just because its address is `localhost`: a local proxy (freellmapi, LiteLLM) can still forward to a cloud model.
- Fully local (no cloud model at all): pick `api` as the brain in setup (option 5) and point it at Ollama, LM Studio or your own vLLM server. Pentarch then runs the tool loop itself, with a small fixed tool set: read and list files in your notes and the Pentarch folder (never `secrets/`), write in the notes folder, and its own commands (reminders, tasks, routines, search, shifts). No shell and no web, so it does less than a real agent CLI; scheduled runs only read, and runs that carry outside text (mail, a job posting) get no tools at all. Your endpoint must be marked `"trusted": true` (setup asks), or the chat won't send it personal data. Pick a model that handles tool calls (Qwen 2.5/3, Llama 3.1+); one without them still chats, just without tools.
- The bot answers the chat that paired with the code and ignores everyone else. The code is 16 hex characters, and after 20 wrong `/start` tries it is thrown away. The panel only listens on `127.0.0.1` and opens only from the link the shortcut (or `python -I app/pentarch.py panel`) gives you; that link sets a cookie, and a plain visit to `http://127.0.0.1:47824/` gets nothing. The secret lives in `~/.pentarch/secrets/panel.token`, which the agent is not allowed to read. This guards against other websites and other local accounts, not against programs running as you, which can read that file. Don't run Pentarch on a shared machine.
- The agent is not allowed to read `~/.pentarch/secrets` (checked with Claude Code: a `--disallowedTools` Read rule refuses it, and shell commands that name the folder or the key files are refused too). A web page that tells the agent to read your keys gets a refusal. Gemini CLI, Codex and OpenCode have no such deny rule, so with them the folder is protected only by the agent following its instructions; if that matters to you, use Claude Code or run outside code in the sandbox (`sandbox.backend`).
- The agent CLI starts without Pentarch's own Telegram, mail, Discord and Slack secrets in its environment, so a command it runs can't print them. API keys for helper models are still passed.
- A scheduled run that decides the work needs the deep model doesn't start it; it becomes a Yes/No proposal like any other.
- Text found in mail, web pages or files is treated as data, never as an instruction or a permission.
- Every reply is checked before it goes out. A year or date that doesn't fit gets a warning line, and numbers that appear nowhere in your message are logged. The check never blocks a reply.
- Your home folder path, passwords written as `password: ...` and Bearer tokens are masked in logs.
- Routines and queued tasks each have a daily dollar budget you set in the panel, and one task run has its own ceiling (Claude Code only).

### Where it connects

Nothing leaves your machine except these:

| Where | Why |
|---|---|
| `api.telegram.org` | your chat with the bot, plus a health check |
| your agent CLI's own service | whatever Claude Code, Gemini CLI, Codex or OpenCode talk to |
| `chat_api` and council seat URLs | only the ones you set; none by default |
| your mail server, `discord.com`, `cdn.discordapp.com` (attachments), `slack.com` and `files.slack.com`, Signal's servers (via signal-cli) | only if you turn those gateways on, or connect your inbox for the mail check (IMAP, read-only: sender, subject and, with Claude Code, the first 300 characters, judged by a run with no tools; OpenCode has no tool-free mode, so it skips mail) |
| `speech.platform.bing.com` (edge-tts) | spoken answers to voice notes (`voice_replies`; Piper runs locally when offline) |
| `boards-api.greenhouse.io`, `api.lever.co`, `api.eu.lever.co`, `api.ashbyhq.com`, `apply.workable.com`, `<company>.recruitee.com`, `api.smartrecruiters.com`, `<company>.jobs.personio.de` / `.com` | job tracker, only for the companies you list |
| `remotive.com`, `arbeitnow.com`, `remoteok.com` | job tracker, only the feeds you list |
| `devpost.com` | the opportunities routine |
| `api.github.com` | application packages: your public repos and merged PRs, read without a token |
| `health_urls` | extra addresses you ask it to watch |
| `google.com`, `api.telegram.org` | the internet check in `doctor` |
| `github.com` | the nightly `git pull --ff-only` auto-update of this repo (the `guncelle` routine, off until you turn it on in setup or the panel). The pulled code runs after the next restart, unreviewed, so you are trusting this repo's `main` branch |
| `pypi.org`, `registry.npmjs.org` | setup only: Python packages and the agent CLI |
| `huggingface.co` | first voice note only: the local Whisper model download |

Local only: the panel on `127.0.0.1`, and Ollama on `127.0.0.1:11434` for memory search if you run it.

## Without a model

The job tracker needs no agent and no API key. If setup finds no agent CLI it says so and lets you carry on or stop; these two commands work either way, on any machine with Python:

```bash
python -I tracker/scan.py --config tracker/config.json    # pulls your job boards and feeds, scores each posting 1-5 (0 = dropped)
python -I tracker/build.py --config tracker/config.json   # writes the offline dashboard to tracker/out/index.html
```

`tracker/config.json` comes from the career step of setup (when you answered yes to the job question), or from `python tracker/build.py --init`; run that first if the file is missing. Scoring is a fixed rule set (title, location, years asked, your skills, how fresh the posting is), so two runs on the same boards give the same answer. [`tracker/README.md`](tracker/README.md) has the config, the rules and the file formats.

## Development

```bash
python -I -m unittest discover -s tests -p "test_*.py"   # unit tests, no network, no model (more in CONTRIBUTING.md)
python -I tests/e2e.py                                      # end-to-end against a fake Telegram and a fake agent
```

Some internal names are Turkish (routine names like `sabah` for the morning brief, files like `kurallar.md`). The project started in Turkish and renaming every file would break existing installs. Everything you see as a user follows your language setting.

MIT license. Fonts in `app/fonts` are under the SIL Open Font License.

---

## Türkçe

Pentarch, kendi bilgisayarında çalışan ve seninle Telegram'dan konuşan kişisel bir asistan. Zaten kullandığın AI ajanıyla çalışır: Claude Code, Gemini CLI, Codex ya da OpenCode. Ona anlattıklarını hatırlar, gün boyu kendi rutinlerini yürütür, geri alınamayacak bir şey yapmadan önce sana sorar.

### Neden

Sohbet uygulamaları sekmeyi kapatınca seni unutur. "Ajan" projelerinin çoğu da merhaba demeden önce sunucu, veritabanı ve bir sürü API anahtarı ister. Pentarch ise makinende çalışan tek bir Python süreci. Zaten giriş yaptığın ajan CLI'ını kullanır, seninle ilgili bildiği her şeyi açıp düzenleyebileceğin düz markdown dosyalarında tutar, sana zaten kullandığın yerden ulaşır: Telegram ya da, Telegram istemiyorsan, e-posta, Discord, Slack veya Signal.

Sıradan bir gün şöyle geçer. Sabah 09:00'da kısa bir özet gelir: bugün ne var, kimden cevap bekliyorsun, önce neyi yapmanı önerir. Otobüste sesli not atarsın, not bilgisayarında yazıya dökülüp dosyalanır. Bir rutin profiline uyan bir ilan bulur ve Evet/Hayır butonlarıyla panoya ekleyip eklemeyeceğini sorar. Akşam günün özeti gelir, gece hafızasını toparlar. Bunların hiçbiri senin adına mesaj atmaz, kod göndermez, dosya silmez. Dışarıya dönük her iş senin "evet"ini bekler.

### Neler yapıyor

- **Sohbet:** Telegram'dan yazı, fotoğraf, sesli mesaj ve butonlar. Claude Code ile sohbet bütün gün tek oturumda kalır, cevaplar hızlı gelir. Zor sorular kendiliğinden daha güçlü modele geçer. İstersen e-posta, Discord, Slack ve Signal'den de konuşabilirsin; hepsi varsayılan olarak kapalı ve yalnızca sana cevap verir. WhatsApp yok, çünkü resmi API mesajları sadece internete açık bir HTTPS adresine gönderiyor.
- **Ses:** Sesli notlar bilgisayarında yazıya dökülür (faster-whisper), "ıı" gibi dolgu sesleri ayıklanır. `whisper.groq_key_env` alanına Groq anahtarının bulunduğu ortam değişkeninin adını yazarsan ses önce Groq'a gider (daha hızlı ama ses bilgisayarından çıkar), olmazsa yerel whisper'a döner. İstersen sesli de cevap verir. Windows'ta bas-konuş da var (varsayılan kapalı): F9'u basılı tutup konuşursun, bırakınca kayıt sesli not gibi gider. ffmpeg ve `push_to_talk.mic` ister.
- **Görüşme asistanı:** `python -I app/pentarch.py meeting "başlık"` yerel bir sayfa açar. Meet ya da Zoom'daki karşı tarafı yazıya döker, `meeting.goal` hedefine göre soru önerir, sana bir şey sorulunca cevap taslağı çıkarır. Sonunda dökümü ve özeti notlarına kaydeder. Ses diske hiç yazılmaz. `pip install soundcard numpy faster-whisper` ister.
- **Panel:** `http://127.0.0.1:47824` adresinde yerel bir sayfa var: sohbet, sağlık durumu, harcama, hatırlatmalar, iş panosu, onay bekleyen öneriler ve bütün ayarlar. Telefon boyutunda da düzgün görünür. `python -I app/pentarch.py panel` açar ve bağlantıyı yazar; başka bilgisayardan `ssh -L 47824:127.0.0.1:47824 <bu makine>` çalıştırıp aynı bağlantıyı aç.
- **Hafıza:** Profilin, her gece toparlanan bir hafıza sayfası, kurallar dosyası, notlarında ve eski sohbetlerde hızlı arama. İstersen (`learning.enabled`) her sohbetten sonra ucuz bir model hafızaya not eklemeyi önerebilir. Sen `onayla N` demeden hiçbir şey yazılmaz.
- **Rutinler:** Sabah özeti, akşam özeti, kontrol listesi, beklediğin cevapların takibi, alanındaki haberler, notlarından çıkan yaklaşan son tarihler, haftalık "ne ters gitti" değerlendirmesi. Hepsi panelden kapatılabilir. Özetler takvimini ajanın takvim aracından, ya da hangi CLI olursa olsun gizli bir iCal adresinden okur (Google'da "iCal biçimindeki gizli adres", Outlook'ta "Takvimi yayımla"): `secrets/keys.env` içine `PENTARCH_ICAL=<adres>` yaz; ajan adresi hiç görmez.
- **Hatırlatma ve görev:** "Yarın 10'da hatırlat" ya da "bunu bu gece yap" dersin, vaktinde çalışır. Görevler günlük bütçe sınırıyla kendi oturumlarında koşar.
- **Sorumluluklar:** Asistanın kendi üstüne aldığı kalıcı bir hedef. Mesela "başvuru listemi güncel tut" ya da "CI yeşile dönene kadar bu repoyu izle". Ya belli aralıklarla ya da bir komutun çıktısı değişince uyanır, kendi notunu tutar, iş sürerken seni rahatsız etmez. Sana yalnızca iş bitince, karar senin olduğunda ya da acil bir şey çıktığında yazar.
- **Kendi rutinlerin:** Bitiş hedefi olmayan, saati gelince tekrar eden işler. Mesela "her pazartesi 9'da açık PR'larımı özetle". Hızlı modelde salt okuma yapar, değişiklik gerekirse öneri olarak sorar. Sohbette iste ya da kendin ekle: `python -I app/pentarch.py rutin ekle prs pzt@09:00 "açık PR'larımı özetle"` (her gün için `08:30`, ayın o günleri için `1,15@09:00`, yalnız belli aylar için `"20@09:00 oca,nis,tem,eki"` (çeyreklik vergi günü gibi), 09:00-23:00 arası 90 dakikada bir için `90dk`, kendi aralığın için `90dk@07:00-01:00`; `rutin liste | dur | devam | sil <ad>`).
- **Öneriler:** Bir rutin işine yarayacak bir şey bulursa Evet/Hayır butonlarıyla sorar.
- **Süren işe not:** Uzun bir iş sürerken bir şey eklemek istersen yaz, o işe gider. Claude Code'da iş bir sonraki araç çağrısından sonra notu okur; diğer CLI'larda iş bitince iletilir. Biten bir görev, senden karar gerektirmeyen ve dışarıya bir şey göndermeyen bir sonraki adımı kendisi sıraya koyabilir.
- **Konsey (`konsey: soru`):** Birkaç model aynı soruyu aynı anda alır. Cevap verirler, birbirlerinin cevabını okurlar, ikinci turda tartışıp oy verirler.
- **Tartışma (`tartışma: konu`):** Konseydeki her model fikir yazar, fikirler iki tur eleştirilir, oylanıp puanlanır, sonunda derin model birini seçer. 10-40 dakika sürer.
- **`/konsey fikir` (Claude Code):** Dört danışman (Savunucu, Şüpheci, İşveren, Uygulayıcı) tek bir fikre ayrı ayrı bakar, bir hakim de BUILD, FIX FIRST ya da KILL kararı verir. Kararın yanında en büyük riski ve 10 dakikalık bir testi de yazar, kararı notlarına kaydeder.
- **Kariyer:** Hackathon ve uzaktan junior ilanlarını takip eder, vize sponsorluğu vermeyen ilanları işaretler, GitHub PR'larını izler. Modelsiz çalışan bir başvuru panosu da var. LinkedIn ve CV becerileri taslak yazar, profilini puanlar ama hiçbir zaman senin yerine paylaşım yapmaz. Her sabah en iyi yeni ilanlardan dördüne aynı anda başvuru paketi hazırlanır: CV, ön yazı, kısa bir mail ve LinkedIn notu. CV'ler profilinden ve GitHub'ının ölçülen verisinden yazılır, ikinci bir model ilana göre 100 üzerinden puanlar, zayıf çıkanı bir kez düzeltir. Başvur ve mail at adımları sana Evet/Hayır diye gelir. Mail adımı yalnızca e-posta kapısını açtıysan çıkar (`gateways.email`, ayrıntılı kurulumda ya da panelde); hızlı kurulum bunu açmaz. `apply` becerisi formu doldurur, her değeri profilinle karşılaştırır ve sen o başvuruya evet demeden göndermez.
- **İsteğe bağlı ekstralar:** Windows bildirim süzgeci, masaüstü kontrolü, Docker'da kum havuzu, kotalı internet modu. Bir de gölge modu var: kısaltma ve ayıklama işleri ikinci bir adreste (`shadow.base_url`) de çalışır, iki cevap yan yana kaydedilir. Böylece daha ucuz bir modelin işi görüp görmediğini anlarsın. Sana her zaman asıl cevap gelir.
- **Kademeli yönlendirme (`routing.enabled`):** Defterdeki işler önce ucuz modelde başlar, bir kontrol cevabı yetersiz bulursa daha güçlü modele geçer. `python -I app/pentarch.py routing` son haftayı gösterir.
- **Gece kendini geliştirme (`self_improve.enabled`):** 03:50'de günün hatalarına bakar, düzeltmeleri Evet/Hayır diye önerir. Kod değişikliklerini yalnızca `.patch` dosyası olarak yazar, uygulamak sana kalır.

### Kurulum

Gerekenler: Windows 10/11, Linux, macOS ya da bir Android telefon, Python 3.10+, [Node.js](https://nodejs.org/) (ajan CLI'ını npm kurar), [git](https://git-scm.com/downloads) ve bir Telegram hesabı. Ajan CLI'ı kurulu değilse ya da giriş yapılmamışsa kurulum ikisini de yapmayı önerir. Bütün özellikleri yalnızca Claude Code ile alırsın. Gemini CLI, Codex ve OpenCode'da sohbet günde tek oturumda kalır ama bütçe ve güvenlik kancaları olmaz. Sohbetten istediğin hatırlatma ve rutinler orada da kaydedilir (ajan `HATIRLAT:` ya da `RUTIN:` satırı yazar, Pentarch saklar ve ne sakladığını söyler). Genel "şu maili gönder" özelliği yok; giden mail yalnızca iş başvurusu ve takibi, o da senin Evet'inle.

**Windows'ta tek satır:** Başlat menüsünden PowerShell'i aç, şunu yapıştır, Enter'a bas:

```powershell
irm https://raw.githubusercontent.com/RizgarOzan/pentarch/main/install.ps1 | iex
```

Git, Python ya da Node.js eksikse kurmak için sorar (winget ile). Kurduktan sonra yeni bir PowerShell penceresi açıp aynı satırı tekrar çalıştırman istenebilir. Linux ve macOS'ta: `curl -fsSL https://raw.githubusercontent.com/RizgarOzan/pentarch/main/install.sh | sh`.

**Elle kurulum (ileri seviye):**

```bash
git clone https://github.com/RizgarOzan/pentarch.git
cd pentarch
python -m venv .venv
.venv\Scripts\python setup.py      # Linux/macOS: .venv/bin/python setup.py
```

Kurulum Türkçe ya da İngilizce konuşur, nerede olduğunu "Adım 3/6" diye gösterir ve her parçayı o anda dener. Önce Python, git ve npm var mı diye bakar; eksik olanın nereden indirileceğini yazar.

**Asistan senin bilgisayarında çalışır.** Bilgisayar kapalıyken ya da uykudayken Telegram'dan cevap vermez, rutinler de o saatte çalışmaz. Sürekli açık kalmasını istiyorsan Android telefona ya da bir sunucuya kur.

**Hızlı kurulum** varsayılan. Yalnızca şunları sorar:

1. **Temel bilgiler:** senin adın ve asistanın adı.
2. **Ajan**, yani asistanın düşünmek için çalıştırdığı program. Emin değilsen: Claude aboneliğin varsa Claude, yoksa Gemini (Google hesabıyla ücretsiz). Kurulu değilse `npm i -g` satırını senin yerine çalıştırmayı önerir. Sonra tek kelimelik bir deneme mesajı atar; giriş yoksa ne yazacağını söyler, giriş için pencere açabilir, bitirince yeniden dener. Claude seçersen planını da sorar.
3. **Telegram:** @BotFather'da `/newbot` ile bot yap, token'ı yapıştır. En kolayı bilgisayarda web.telegram.org'u açıp oradan kopyalamak.
4. **Ücretsiz anahtarlar:** OpenRouter ve Groq (ücretsiz katman), sonra NVIDIA (biten deneme kredisi), sırayla. Hızlı kurulumda varsayılan cevap "hayır"; evet dersen o servisin anahtar sayfasını tarayıcıda açar (NVIDIA'nınki build.nvidia.com'da) ve adım adım anlatır. Hepsi isteğe bağlı: asistan ucuz işleri bunlara verir, konseye koltuk olurlar.
5. **Kurulum:** iş ya da staj arayıp aramadığını sorar (evet dersen kariyer soruları gelir; yalnızca staj için `intern` seç, Türkiye'de bir yer yazarsan Türk şirketlerinin ilan panolarını önerir). Gelen kutunu okuyup okumayacağını da sorar (Gmail için uygulama şifresi gerekir, nasıl alınacağını anlatır). Geri kalan her şey varsayılanını alır. Sesli mesaj paketleri (yaklaşık 300 MB) iner, Windows'ta açılışa ve masaüstüne kısayol eklenir; ekranda ne yaptığını yazar.
6. **Eşleşme ve başlatma:** botuna giden bir `t.me` bağlantısı açar. Telegram'da Start'a basınca kurulum bunu görür, bot sana selam yazar. Sonra asistanı arka planda başlatmayı önerir.

**Ayrıntılı kurulum** (ilk soruya "hayır") not klasörünü, üç modeli, izin modunu, ek bir API'yi (Ollama, LM Studio ya da kendi adresin), konsey koltuklarını, kariyer filtrelerini, MCP sunucularını (hangi ajanı seçtiysen ona verilir: Claude Code, Gemini CLI, Codex ya da OpenCode), rutinleri ve kısayolları da sorar. `insa` (gece kendini geliştirme) ve `posta` (posta kontrolü) iki durumda da kapalı başlar. Kurulumu istediğin zaman yeniden çalıştırabilirsin, verdiğin cevapları korur. Yarıda bırakırsan baştan başla: kaldığı yerden devam etmez, ama bir kez biten kurulumun cevapları varsayılan olarak geri gelir.

**Anahtarları almak:** Kurulum sorduğu her anahtar için servisin ne olduğunu, gerekip gerekmediğini ve ücretsiz katmanı olup olmadığını söyler. Kayıt ve anahtar sayfasını yazar, sayfayı tarayıcıda açmayı önerir, adımları sıralar. Anahtarı yapıştırınca önce biçimine bakar, sonra servise ücretsiz bir istek atıp kabul edip etmediğini dener. Kabul etmezse nedenini söyler, yeniden yapıştırmanı ister. İsteğe bağlı bir anahtarı boş bırakıp Enter'a basarsan atlanır; sonra kurulumu yeniden çalıştırıp ekleyebilirsin.

| Servis | Ne için | Gerekli mi | Ücretsiz | Kayıt | Anahtar sayfası |
|---|---|---|---|---|---|
| Telegram | konuştuğun bot | evet, Telegram'dan konuşmak için | ücretsiz | [telegram.org/apps](https://telegram.org/apps) | [@BotFather](https://t.me/BotFather), `/newbot` gönder |
| OpenRouter | ucuz işler, konsey koltukları | isteğe bağlı | `:free` modeller, dakikada 20, günde 50 istek | [openrouter.ai](https://openrouter.ai/) | [openrouter.ai/keys](https://openrouter.ai/keys) |
| Groq | ucuz işler, sesli notlar | isteğe bağlı | ücretsiz plan | [console.groq.com](https://console.groq.com/) | [console.groq.com/keys](https://console.groq.com/keys) |
| NVIDIA | ucuz işler, konsey koltukları | isteğe bağlı | deneme kredisi | [build.nvidia.com](https://build.nvidia.com/) | [API anahtarları](https://build.nvidia.com/settings/api-keys) |
| Anthropic | Claude'u kullandıkça öde (`plan = api`) | yalnızca `plan = api` için | yok, önce kredi yüklenir | [platform.claude.com](https://platform.claude.com/) | [settings/keys](https://platform.claude.com/settings/keys) |
| Ollama, LM Studio | modelleri kendi bilgisayarında çalıştırmak | isteğe bağlı | ücretsiz, anahtar yok | [ollama.com/download](https://ollama.com/download), [lmstudio.ai](https://lmstudio.ai/) | yok |

`python -I app/koltuk.py add` ile konsey koltuğu eklerken de aynı rehber çalışır. NVIDIA anahtarı denenmez, çünkü model listesi herkese açık ve bir sohbet isteği kredi harcar.

Ayarlar, hafıza ve anahtarlar `~/.pentarch` içine gider. Repoda yalnızca başvuru panosunun kendi dosyaları kalır, onlar da gitignore'da. Kurulum, kendisini hangi Python ile çalıştırdıysan onu kullanan bir başlangıç kısayolu ekler; bu yüzden venv içinden çalıştır. `requirements.txt`'i kurmayı da önerir. Bunun yaklaşık 300 MB'ı isteğe bağlı yerel ses paketi.

**İlk çalıştırma:** Kurulum başlatmadıysa, bitişte yazdığı komutu kopyalayıp çalıştır (Pentarch klasöründeki venv Python'unu tam yoluyla kullanır). Eşleşmeyi atladıysan botuna `/start <kod>` yaz. Kod, kurulumun gösterdiği kod; `~/.pentarch/secrets/telegram-pair.txt` dosyasında da duruyor. Doğru kodu gönderen sohbet sahip olur, başkalarından gelen mesajlar yok sayılır.

**Kontrol ve güncelleme:** `python -I app/pentarch.py doktor` ayar dosyasına, not klasörüne, ajan CLI'ına, ffmpeg'e, Telegram token'ına, ayarlarda adı geçen anahtarlara ve iki porta bakar, her satırı OK ya da `!!` diye işaretler. İnternete de bakar. Windows'ta son bir günde çöken uygulamaları, dolmak üzere olan diskleri ve VPN bağdaştırıcılarını da gösterir. Anahtarların yalnızca tanımlı olup olmadığını söyler, değerini hiçbir zaman yazmaz. `python -I app/pentarch.py guncelle` komutu `git pull --ff-only` çalıştırır ama yalnızca repoda kaydedilmemiş bir değişiklik yoksa. Çalışan Pentarch kod değişince kendini yeniden başlatır. `python -I app/pentarch.py yedek [dosya.zip]` notları, hafızayı, rutinleri ve ayarları tek bir zip'e koyar; anahtarların durduğu `secrets/` klasörü içine girmez.

**Otomatik güncelleme:** `guncelle` rutini varsayılan olarak kapalıdır (kurulumda ya da panelde açarsın); açıksa aynı güncellemeyi her gece 05:10'da kendisi yapar, yeni sürüm geldiyse neyin değiştiğini sana yazar. Yeniden başladıktan sonra yeni ya da değişen becerileri kendisi kurar (`python -I setup.py --upgrade`); senin düzenlediğin bir beceriye dokunmaz. Şablona yeni numaralı kurallar eklendiyse onları `kurallar.md`'ye ekler (eski hâli `kurallar.md.bak` olarak kalır); senin yazdığın kurallar olduğu gibi durur. Klasöre kendi eklediğin dosyalar güncellemeyi durdurmaz. Repodaki dosyalarda senin değişikliğin varsa çekmez, sadece not düşer; yani yaptığın değişiklikler ezilmez. Kapatmak için `python -I setup.py` içindeki otomatik güncelleme sorusuna "hayır" de ya da panelde Ayarlar > Kapalı işler'e `guncelle` ekle.

**Eski kurulumu güncellemek:** Otomatik güncelleme gelmeden önce kurduysan bir kereye mahsus elle güncellemen gerekiyor, sonrasını gece rutini halleder. Bir yapay zekâ kod ajanı kullanıyorsan (Claude Code, Codex, Cursor vb.) Pentarch klasöründe açıp şunu yapıştır:

```text
Bu klasör benim Pentarch kurulumum. `git status` çalıştır. Yerel değişiklik varsa listele ve hiçbir şeye dokunmadan bana ne yapacağımı sor. Temizse `git pull --ff-only` çalıştır, eski commit'ten yenisine `git log --oneline` ile neyin değiştiğini birkaç satırda anlat, sonra `python -I setup.py` çalıştır ve yeni soruları benimle birlikte cevapla. Hiçbir şeyi silme ya da sıfırlama.
```

Ajan yoksa Pentarch klasöründe: `git pull --ff-only`, ardından `python -I setup.py`.

**Android:** Telefon tek başına da çalıştırabilir. Adımlar yukarıdaki "On an Android phone" bölümünde. Kısaca: F-Droid'den Termux ve Termux:Boot kur, Gemini CLI'a Google hesabıyla giriş yap, Termux'u pil optimizasyonundan çıkar. iPhone'da bu olmaz, çünkü iOS bir uygulamanın sürekli sunucu çalıştırmasına izin vermiyor.

### Ayarlar ve komutlar

Ayarlar `~/.pentarch/pentarch.json` dosyasında. Yazmadığın her ayar [`app/config.py`](app/config.py) içindeki varsayılan değeri alır. Panelin Ayarlar sayfası da aynı dosyayı düzenler. Anahtarların listesi yukarıdaki "Configure" tablosunda. Komutların Türkçesi de çalışır: `iptal`, `durdur 2 saat`, `devam`, `konsey: soru`, `ogren`, `onayla N`, `sil N`, `/ekle not`, `/sor soru`, `/durum`, `internet serbest`.

**Konsey koltukları:** `python -I app/koltuk.py add AD --preset AD` ile eklenir (`openrouter`, `groq`, `nvidia`, `freellmapi`, `ollama`, `lmstudio`, `custom` ya da `--agent`). Ayrıca `list`, `test AD` ve `remove AD` var. Bota "konseye koltuk ekle" demen de yeter. Anahtarı sohbete düz yazma. `koltuk.py key DEGISKEN` ile ver ya da bota `anahtar: DEGISKEN=değer` yaz; bot anahtarı kaydeder ve mesajı siler.

**Slack, Signal, Discord:** tam kurulum (hızlı mod değil) her birini sorar ve token'ı kaydeder. Elle yapmak istersen `pentarch.json` içine `gateways` bloğunu ekleyip Pentarch'ı yeniden başlat. Örnek blok ve her birinin adımları yukarıda, "Turning on Slack, Signal or Discord" başlığında. Token'ı `koltuk.py key PENTARCH_SLACK_TOKEN` ile kaydet. İlk tur sadece yeri işaretler; Pentarch açılmadan önce gelen mesajlara cevap vermez. Gönderilemeyen bir cevap saklanır ve yeni mesajlara bakmadan önce tekrar gönderilir.

### Pro ile kullanım

Pro ya da Max planında Claude Code, claude.ai ve Claude Desktop ile aynı kullanım sınırını paylaşır. Bir sınır 5 saatte bir sıfırlanır, bir de haftalık sınır var. İkisini de Ayarlar > Kullanım'da ya da Claude Code'da `/usage` ile görürsün. Max, Pro'nun 5 ya da 20 katını verir. Ortamda `ANTHROPIC_API_KEY` tanımlıysa Claude Code plan yerine API'den ücret keser. Pentarch'ın rutinleri gün boyu arkada çalıştığı için Pro'da kendi sohbetlerine ayırdığın payı yiyebilir.

`setup.py` hangi planda olduğunu soruyor. `"plan": "pro"` seçince şunlar değişir:

- Zamanlı işler hafif açılır. Kullanıcı ayarlarını, CLAUDE.md'yi, eklentileri ve skill'leri yüklemez, sadece kullandığı yerleşik araçları alır. Bağlayıcı araçları ToolSearch arkasında bekler. Salt okunur kanca yine çalışır.
- Kalp atışı ve aralıklı öteki işler yarı sıklıkta koşar. Saati belli olanlar (sabah, akşam, hafıza, pano, güncelleme) saatini korur.
- Gece wiki turu hafif modelle koşar, keşif kapalı başlar. Panelden açabilirsin.
- Günlük tavanlar rutinler için 2 dolara, görevler için 8 dolara iner, inisiyatif günde bire düşer. Bunlar claude'un kendi maliyet raporundaki API karşılığı rakamlar, ölçü olsun diye var. Senden bu parayı kimse almaz.
- Sohbet her turda bütün bağlamı yeniden okuduğu için oturum daha erken, 60 bin token civarında yenilenir.
- Claude sınırın dolduğunu söyleyince Pentarch rutinleri ve görevleri hatadaki sıfırlanma saatine kadar durdurur, sana da bir kez haber verir.

2026-11-15'te gerçek rutin prompt'larını aynı kod yolundan geçirip ölçtüm. Rakamlar koşu başına token, önbellekten okunanlar dahil:

| Rutin | `max` | `pro` | Sonuç |
|---|---|---|---|
| kalp | 224k | 41-44k | aynı (`-`, söylenecek bir şey yok) |
| sabah | 174k | 72k | aynı yapı, gerçek bir fırsat seçti |
| akşam | 168k | 63k | aynı yapı |
| wiki | 368k | 127k | aynı notları dosyaladı, aynı soruyu sordu |

Boş bir koşu 54-59 binden 10 bine indi. ToolSearch'ü çıkarınca iş kötüleşti, bütün bağlayıcı şemaları yüklendi ve boş bir tur 186 bin tuttu. Kalp atışını haiku ile de denedim, vazgeçtim. İki koşunun birinde sonnet'in sessiz kaldığı yerde "yeni bir şey yok" mesajı attı.

Kaynaklar yukarıdaki "Using with Pro" bölümünün sonunda.

### Modelsiz kullanım

Başvuru panosu ve ilan taraması ne ajan ne de anahtar ister. `python -I tracker/scan.py --config tracker/config.json` ilanları çekip 1-5 arası puanlar. `python -I tracker/build.py --config tracker/config.json` panoyu `tracker/out/index.html` dosyasına yazar. Kurulum ajan CLI'ı bulamazsa bunu söyler, devam edip etmemeyi sana bırakır.

### Güvenlik

- Ajana gönderme, paylaşma, push ve silmeden önce sorması söylenir; rutinler Evet/Hayır butonlarıyla sorar. Mail ve iş başvurusu yalnızca o butonlardan çıkar. Claude Code'da zamanlanmış işlere bir kanca da takılır: e-posta gönderme, takvim, Drive ve Notion'a yazma, `git push`/`commit` ve `gh` yazma işlerini durdurur. Bu bir yasak listesi, kum havuzu değil: `rm`'yi ya da düz bir HTTP isteğini durdurmaz, Gemini, Codex ve OpenCode'a da takılmaz. Gerçek yalıtım için `acceptEdits` modunda kal ve Docker kum havuzunu aç, ya da Pentarch'ı bir sanal makinede veya konteynerde çalıştır. `bypassPermissions` modunda kum havuzu ajanın uyduğu bir kural olur, duvar değil.
- Anahtarlar `~/.pentarch/secrets` içinde durur. Ne prompt'a ne log'a ne de repoya girer. Bir API modeline giden metindeki anahtarlar `[secret]` ile değiştirilir.
- Claude Code bu klasörü okuyamaz; kural bunu engeller. Gemini CLI, Codex ve OpenCode'da böyle bir kural yok, orada klasörü yalnızca ajanın talimata uyması korur. Bu senin için önemliyse Claude Code kullan ya da dışarıdan gelen kodu kum havuzunda çalıştır (`sandbox.backend`).
- Ajan CLI'ı Pentarch'ın kendi Telegram, mail, Discord ve Slack sırları olmadan başlar; çalıştırdığı bir komut bunları göremez. Yardımcı modellerin API anahtarları yine geçer.
- Zamanlanmış bir koşu işin derin model istediğine karar verirse işi kendisi başlatmaz, Evet/Hayır önerisi olarak sorar.
- Bot yalnızca kodla eşleşen sohbete cevap verir. Panel yalnızca `127.0.0.1` adresini dinler ve sadece kısayolun (ya da `python -I app/pentarch.py panel` komutunun) verdiği bağlantıyla açılır; düz `http://127.0.0.1:47824/` ziyareti hiçbir şey almaz. Gizli anahtar `~/.pentarch/secrets/panel.token` dosyasında, ajan o dosyayı okuyamaz. Yani panel başka web sitelerine ve bilgisayardaki başka hesaplara karşı korur, senin hesabınla çalışan programlara karşı korumaz. Ortak kullanılan bir bilgisayarda çalıştırma.
- E-postada, web sayfasında ya da dosyada geçen yazılar talimat sayılmaz, yalnızca veri olarak okunur.
- Her cevap gitmeden önce kontrol edilir. Tutmayan bir yıl ya da tarih varsa cevaba uyarı satırı eklenir. Senin mesajında hiç geçmeyen sayılar log'a yazılır. Bu kontrol cevabı hiçbir zaman durdurmaz.
- Log'larda ev klasörünün yolu, `şifre: ...` diye yazılmış parolalar ve Bearer token'ları maskelenir.
- Sohbetin günlük harcamasına sınır koyabilirsin (`chat_daily_usd`).
- Makineden dışarıya hangi adreslere bağlandığı yukarıdaki "Where it connects" tablosunda yazıyor.
