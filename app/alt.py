"""Subagents: run several agent CLI tasks side by side and collect the answers.

  python -I alt.py "task one" "task two" ...    # prints each answer under its task
  python -I alt.py --n 2 --model haiku "a" "b"  # at most 2 at once, model for every task

Each task is a fresh, headless run of the configured agent CLI (no shared session), in the notes folder.
"""
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import agents  # noqa: E402
from config import C, EXTRA_DIRS, NOTES, T  # noqa: E402


def tek(gorev, model=None, timeout=1800):
    """One headless run; the same dict shape as claude's JSON output (result, is_error, total_cost_usd)."""
    if agents.CLI != "claude":
        return agents.run_other(gorev, model, timeout, cwd=NOTES)
    a = C["agent"]
    cmd = [agents.exe(), "-p", "--output-format", "json", "--permission-mode", a["permission_mode"],
           *(["--model", model] if model else [])]
    if a["permission_mode"] != "bypassPermissions":
        cmd += ["--allowedTools", ",".join(a["allowed_tools"])]
    for d in EXTRA_DIRS:
        cmd += ["--add-dir", str(d)]
    try:
        p = subprocess.run(cmd, input=gorev, cwd=NOTES, capture_output=True, encoding="utf-8", errors="replace",
                           timeout=timeout, creationflags=agents.NO_WINDOW)
        return json.loads(p.stdout)
    except subprocess.TimeoutExpired:
        return {"result": T(f"(zaman aşımı: {timeout} sn)", f"(timed out after {timeout} s)"), "is_error": True}
    except ValueError:
        return {"result": (p.stderr or p.stdout).strip()[-500:] or "(no output)", "is_error": True}


def paralel(gorevler, n=4, model=None, kos=tek):
    """Runs the tasks at most `n` at a time; results come back in task order. One failing task doesn't stop the rest."""
    def guvenli(g):
        try:
            return kos(g, model)
        except Exception as e:
            return {"result": f"(error: {e!r})"[:500], "is_error": True}
    with ThreadPoolExecutor(max_workers=max(1, min(n, len(gorevler) or 1))) as ex:
        return [{"gorev": g, **r} for g, r in zip(gorevler, ex.map(guvenli, gorevler))]


def main():
    args, n, model = sys.argv[1:], 4, None
    for bayrak in ("--n", "--model"):
        if bayrak in args:
            i = args.index(bayrak)
            n, model = (int(args[i + 1]), model) if bayrak == "--n" else (n, args[i + 1])
            args = args[:i] + args[i + 2:]
    if not args:
        sys.exit(__doc__)
    sys.stdout.reconfigure(encoding="utf-8")
    for r in paralel(args, n, model):
        print(f"## {r['gorev'][:80]}{' (error)' if r.get('is_error') else ''}\n{r.get('result', '')}\n")


if __name__ == "__main__":
    main()
