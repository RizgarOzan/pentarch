# Skills

Instructions an AI assistant follows for one kind of task, plus a small script they share. They draft; you post and send. None of them opens LinkedIn, sends a message or needs a paid API.

| skill | use it when |
|---|---|
| `linkedin-post/` | writing or fixing a post, picking a hook, planning the week, asking why a post did not land |
| `linkedin-profile/` | scoring and rewriting the profile against a 100-point rubric |
| `linkedin-network/` | comments, connection notes and recruiter messages for the companies in your job search, with a follow-up log |
| `linkedin-analyze/` | weekly or monthly review of your own numbers and next week's plan |
| `linkedin/li.py` | the script the four skills call: post checker, profile scorer, post log, contact log |
| `cv/` | a one-page CV for a posting, XYZ bullets, then a rule check with `cv/cv.py` |

## Where they go

They stay here in the repo. `setup.py` writes a one-line pointer for each into `~/.pentarch/beceriler/` (or `$PENTARCH_HOME/beceriler/`), so the Pentarch assistant's memory search attaches the right `SKILL.md` when a request matches it.

With Claude Code as the agent, setup also offers to copy the four `linkedin-*` folders and `cv/` into `~/.claude/skills/`, so `/linkedin-post` and the others work in any Claude Code session. Each `SKILL.md` has the frontmatter Claude Code expects; the copies call `li.py` and `cv.py` from this folder.

## The script

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

Every rule in the skills is marked either as a LinkedIn fact with its source or as a convention, unverified. The log exists so the conventions get replaced by your own numbers.
