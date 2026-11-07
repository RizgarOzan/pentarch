"""Subagents: run several agent CLI tasks side by side and collect the answers.

  python -I alt.py "task one" "task two" ...    # prints each answer under its task
  python -I alt.py --n 2 --model haiku "a" "b"  # at most 2 at once, model for every task

Each task is a fresh, headless run (no shared session), in the notes folder. With agent.workers set (e.g. gemini,
codex) the tasks are spread over those CLIs so more runs fit at once; the main agent (Claude) still plans the work and
checks every answer before using it. `--cli claude` keeps a hard task on the main CLI.
  python -I alt.py --cli claude "hard task"
  python -I alt.py "arastirmaci: X" "elestirmen: Y"   # a role prefix adds that role's brief
  python -I alt.py --roller                           # lists the roles
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import agents  # noqa: E402
import config  # noqa: E402
from config import C, EXTRA_DIRS, NOTES, T  # noqa: E402
WD = NOTES if NOTES.is_dir() else None  # no notes folder on this machine: run where alt.py was started


# Ready roles: "role: task" puts the brief in front of the task. `kritik` roles stay on the main CLI (Claude).
ROLLER = {
    "arastirmaci": "Research on the web and in the notes. Every claim gets its source (URL or [[page]]); keep facts and guesses apart.",
    "okuyucu": "Read the files or pages named and return only what the task asks for, with file:line. No opinions.",
    "kodcu": "Make the smallest change that fully does the task, match the file's style, run the tests and report their real output.",
    "hata_avcisi": "Find real bugs: for each, file:line, a concrete failing input, and a repro you actually ran. Mark unproven ones SUSPECTED.",
    "testci": "Write or run tests for the named code. Report pass/fail with the failing lines only; never claim a pass you didn't see.",
    "elestirmen": "Argue against the plan or text: the strongest reasons it fails, with evidence. End with the one change that matters most.",
    "guvenlik": "Review for security: secrets, injection, unsafe shell, data leaving the machine. file:line and the fix for each.",
    "yazar": "Write the text asked for in the owner's plain voice: short sentences, no filler, no AI tells. Keep every fact given; add none.",
    "cevirmen": "Translate faithfully and naturally; keep code, names and links as they are.",
    "ozetci": "Summarise to the few points that change a decision. Numbers and names stay exact.",
    "wiki": "Work in the wiki: one concept per page, frontmatter, [[links]], a Related line. Never edit raw/.",
    "planlayici": "Break the goal into steps that each stand alone, with how each is verified. Flag the riskiest step.",
    "veri": "Analyse the data: say what you computed and how, give exact numbers, and say what the data can't tell.",
    "dogrulayici": "Check the given answer against the sources yourself. Say CONFIRMED, WRONG (with the fix) or UNVERIFIED for each claim.",
}
KRITIK = {"kodcu", "guvenlik", "dogrulayici", "planlayici"}  # judgement work: the main CLI does these


def rol(gorev):
    """('role', task with the brief) when the task starts with a known 'role:'; else (None, task)."""
    ad, _, geri = gorev.partition(":")
    ad = ad.strip().lower()
    return (ad, f"[Role: {ad}] {ROLLER[ad]}\n\nTask: {geri.strip()}") if ad in ROLLER and geri.strip() else (None, gorev)


def tek(gorev, model=None, timeout=1800, cli=None):
    """One headless run; the same dict shape as claude's JSON output (result, is_error, total_cost_usd)."""
    cli = cli or agents.CLI
    if cli != "claude":
        try:
            return {**agents.run_other(gorev, None if cli != agents.CLI else model, timeout, cwd=WD, cli=cli),
                    "cli": cli}
        except (TimeoutError, OSError) as e:
            return {"result": f"({cli}: {e})", "is_error": True, "cli": cli}
    a = C["agent"]
    cmd = [agents.exe(), "-p", "--output-format", "json", "--permission-mode", a["permission_mode"],
           *(["--model", model] if model else [])]
    if a["permission_mode"] != "bypassPermissions":
        cmd += ["--allowedTools", config.allowed_tools(a["allowed_tools"])]
    for d in EXTRA_DIRS:
        cmd += ["--add-dir", str(d)]
    try:
        p = subprocess.run(cmd, input=gorev, cwd=WD, capture_output=True, encoding="utf-8", errors="replace",
                           timeout=timeout, creationflags=agents.NO_WINDOW)
        return {**json.loads(p.stdout), "cli": "claude"}
    except subprocess.TimeoutExpired:
        return {"result": T(f"(zaman aşımı: {timeout} sn)", f"(timed out after {timeout} s)"), "is_error": True}
    except ValueError:
        return {"result": (p.stderr or p.stdout).strip()[-500:] or "(no output)", "is_error": True}


def paralel(gorevler, n=4, model=None, kos=tek, cli=None):
    """Runs the tasks at most `n` at a time; results come back in task order. One failing task doesn't stop the rest.
    Without `cli`, task i goes to agent.workers[i % len] (the main CLI when the list is empty). A worker that fails
    gets its task retried once on the main CLI, so a free-tier limit never loses work."""
    workers = [cli] if cli else (C["agent"].get("workers") or [agents.CLI])

    def guvenli(i_g):
        i, g = i_g
        ad, g = rol(g)
        w = agents.CLI if ad in KRITIK and not cli else workers[i % len(workers)]
        try:
            r = kos(g, model, cli=w) if kos is tek else kos(g, model)
            if r.get("is_error") and w != agents.CLI and kos is tek:
                r = {**kos(g, model, cli=agents.CLI), "retried_from": w}
            return r
        except Exception as e:
            return {"result": f"(error: {e!r})"[:500], "is_error": True}
    with ThreadPoolExecutor(max_workers=max(1, min(n, len(gorevler) or 1))) as ex:
        return [{"gorev": g, **r} for g, r in zip(gorevler, ex.map(guvenli, enumerate(gorevler)))]


def main():
    args, opt = sys.argv[1:], {"--n": str(C["agent"].get("max_parallel", 8)), "--model": None, "--cli": None}
    for bayrak in opt:
        if bayrak in args:
            i = args.index(bayrak)
            if i + 1 >= len(args):
                sys.exit(f"{bayrak} needs a value")
            opt[bayrak] = args[i + 1]
            args = args[:i] + args[i + 2:]
    if not opt["--n"].isdigit() or int(opt["--n"]) < 1:
        sys.exit("--n needs a positive number")
    n, model, cli = int(opt["--n"]), opt["--model"], opt["--cli"]
    sys.stdout.reconfigure(encoding="utf-8")
    if args == ["--roller"]:
        return print(chr(10).join(f"{k}{' *' if k in KRITIK else ''}: {v}" for k, v in ROLLER.items()))
    if not args:
        sys.exit(__doc__)
    for r in paralel(args, n, model, cli=cli):
        print(f"## [{r.get('cli', '?')}{' <- ' + r['retried_from'] if r.get('retried_from') else ''}] {r['gorev'][:80]}{' (error)' if r.get('is_error') else ''}\n{r.get('result', '')}\n")


if __name__ == "__main__":
    main()
