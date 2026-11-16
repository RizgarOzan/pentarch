# Skills and agents

Skills are instructions an AI assistant follows for one kind of task. Agents are Claude Code subagents a skill hands part of the work to. Everything here drafts, advises or records: nothing opens LinkedIn, sends a message, posts or needs a paid API.

## Skills

| Skill | Use it when |
|---|---|
| [`konsey/`](konsey/SKILL.md) | you want a second opinion on an idea, plan or decision. Four advisors look at it on their own, a judge gives one verdict (BUILD, FIX FIRST or KILL) with the main risk and a 10-minute test, and the verdict goes in your notes. Claude Code only; you start it with `/konsey <idea>` |
| [`ogret/`](ogret/SKILL.md) | you want to learn while the work gets done. It asks how you would solve it first, explains the tradeoffs, leaves you a small piece to write and logs what you learned |
| [`linkedin-post/`](linkedin-post/SKILL.md) | writing or fixing a post, picking a hook, planning the week, asking why a post did not land |
| [`linkedin-profile/`](linkedin-profile/SKILL.md) | scoring and rewriting the profile against a 100-point rubric |
| [`linkedin-network/`](linkedin-network/SKILL.md) | comments, connection notes and recruiter messages for the companies in your job search, with a follow-up log |
| [`linkedin-analyze/`](linkedin-analyze/SKILL.md) | weekly or monthly review of your own numbers and next week's plan |
| [`cv/`](cv/SKILL.md) | a one-page CV for a posting, XYZ bullets, then a rule check with `cv/cv.py` |
| [`apply/`](apply/SKILL.md) | fill an application form, check it with `tracker/apply.py`, send only after the owner's yes |

`linkedin/li.py` is the script the four LinkedIn skills share: post checker, profile scorer, post log and contact log.

## Agents

They live in [`../agents/`](../agents) and are plain Claude Code subagent files.

| Agent | What it does |
|---|---|
| `konsey-savunucu` | Advocate: makes the best honest case for the idea |
| `konsey-supheci` | Skeptic: searches the web for whoever already built it and for the reason to drop it |
| `konsey-isveren` | Employer: reads the idea as a hiring manager for your target roles would (or as its market would, if it has nothing to do with getting hired) |
| `konsey-uygulayici` | Builder: opens your repo, estimates the hours and weighs them against your weekly time |
| `konsey-hakim` | Judge: weighs the four reports and gives the verdict |
| `log-avcisi` | Reads a big log or test output and returns only the finding, so the bulk stays out of your main chat |

The advisors never see each other's reports, and the brief they get is written in neutral words, so none of them can tell which answer you are hoping for. The judge decides on evidence, so one sourced problem can outweigh three compliments.

There are two councils. The Telegram `council:` command asks several different models the same question and lets them vote. `/konsey` is one Claude Code session giving a single idea a structured review from fixed angles.

## Where they go

They stay here in the repo. `setup.py` writes a one-line pointer for each skill into `~/.pentarch/beceriler/` (or `$PENTARCH_HOME/beceriler/`), so the assistant's memory search attaches the right `SKILL.md` when a request matches.

With Claude Code as the agent, setup also offers to copy the skills into `~/.claude/skills/` and the agents into `~/.claude/agents/`, so `/konsey`, `/linkedin-post` and the rest work in any Claude Code session. While copying it fills in your notes folder and Pentarch home, and points the LinkedIn and CV skills at the scripts in this folder. **If you already have a skill or agent with the same name and different content, setup leaves yours alone** and lists what it skipped. Running setup again is safe.

`konsey` reads `~/.pentarch/profile.md` for your goals and weekly hours, so fill that in first. Verdicts go to `<notes>/konsey.md`, newest first; `ogret` writes to `<notes>/learning-log.md`.

## The scripts

```
python skills/linkedin/li.py check post.txt
python skills/linkedin/li.py profile export.json
python skills/linkedin/li.py log add --hook "Number Reveal" --pillar authority --file post.txt
python skills/linkedin/li.py log result 1 --views 900 --comments 7
python skills/linkedin/li.py log stats
python skills/linkedin/li.py network add --name "A. B." --company Acme --why "recruiter, sent application"
python skills/linkedin/li.py network due
python skills/cv/cv.py template
python skills/cv/cv.py check cv.md --jd posting.txt
```

Standard library only. State is two JSON files under `~/.pentarch/linkedin/` (`--home DIR` overrides). Tests: `python -I skills/linkedin/test_li.py` and `python -I skills/cv/test_cv.py`.

Every rule in the LinkedIn skills is marked either as a LinkedIn fact with its source or as an unverified convention. The log exists so your own numbers can replace the conventions.
