# Contributing

Run everything with one command each (no network, no model):

```bash
python -I -m unittest discover -s tests -p "test_*.py"   # main suite
python -I tests/e2e.py                                   # fake Telegram + fake agent
python -I tracker/test_scan.py && python -I tracker/test_apply.py && python -I skills/cv/test_cv.py && python -I skills/linkedin/test_li.py && python -I skills/interview/test_interview.py
```

CI runs all of these (`.github/workflows/ci.yml`). Set `PENTARCH_HOME` to a temp folder first so tests never touch your own install.

## Add a skill
Make `skills/<name>/SKILL.md` with `name:` and `description:` in the frontmatter (copy `skills/cv/SKILL.md`), then add a row to `skills/README.md`. Setup finds the folder and points the agent at it on its own.

## Add a routine
For yourself: no code, add it to `rutinler.json` (see "Routines" in the README). A built-in one is an entry in `JOBS` in `app/pentarch.py`: `at` or `every` (minutes), optional `weekday`, `between`, `if`, `model`, and either a `prompt` or a `run` function (no model; return `"-"` to stay silent). Anything a `run` function sends is already on the owner's chat.

## Add a messaging gateway
All in `app/gecit.py`: the door list in `acik()`, the parse branch in `_parca`, the length limit in `BOY`, the `calis` table and `ev()`. Defaults go in `app/config.py` (`DEFAULTS["gateways"]`). **Also add its token env name to the `own` set in the agent-environment function in `config.py`**, or the token reaches the agent's environment. Tests: copy the mocks around `gecit` in `tests/test_birim.py`.

## Style
Match the file you edit. User-facing strings go through `T(tr, en)`, so both languages stay in step. Some internal names are Turkish because the project started that way; renaming files would break existing installs.
