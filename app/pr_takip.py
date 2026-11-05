"""PR tracking: the owner's open PRs where a maintainer had the last word and nobody answered, and PRs silent for 7+ days.

No packages, no model; uses the `gh` CLI. Comments, reviews and line comments all count, bots are dropped.
    python -I pr_takip.py
    python -I pr_takip.py --taslak   # prints a polite reminder draft under each silent PR; does NOT send it
Needs config "github_user"; when it is empty the script exits quietly. The morning brief runs this and the core
reads lines starting with WAITING / APPROVED (import them from here rather than matching the text).
"""
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import C, T  # noqa: E402

ME = C.get("github_user") or ""
SILENT_DAYS = 7
WAITING = T("Cevap bekliyor", "Awaiting reply")
APPROVED = T("Onaylandı", "Approved")
BOT = re.compile(r"bot\b|\[bot\]|github-actions|codecov|coderabbit|netlify|vercel|sonar|changeset|cla-?assistant|"
                 r"copilot|gemini-code-assist|sourcery|deepsource", re.I)
COMMAND = re.compile(r"^\s*[@/][\w-]+(\s+\w+)?\s*$")  # "@codex review", "/gemini review": a command to a bot, not to you


def gh(*args):
    # called from pythonw; without the flag every gh call opened a console window
    out = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", timeout=60,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if out.returncode:
        raise RuntimeError(out.stderr.strip()[:200])
    return json.loads(out.stdout)


def events(repo, number):
    """Human conversation and commits on a PR: (time, author, kind) sorted by time; bots and bot commands dropped."""
    pr = gh("pr", "view", str(number), "-R", repo, "--json", "comments,reviews,commits,createdAt")
    out = [(pr["createdAt"], ME, T("açılış", "opened"))]
    out += [(c["createdAt"], c["author"]["login"], T("yorum", "comment")) for c in pr["comments"] if not COMMAND.match(c["body"])]
    out += [(r["submittedAt"], r["author"]["login"], "approve" if r["state"] == "APPROVED" else "review")
            for r in pr["reviews"] if r.get("submittedAt")]
    out += [(c["committedDate"], ME, "commit") for c in pr["commits"]]
    out += [(c["created_at"], c["user"]["login"], T("satır yorumu", "line comment"))
            for c in gh("api", f"repos/{repo}/pulls/{number}/comments", "--paginate")]
    return sorted(e for e in out if not BOT.search(e[1]))


def draft(people):
    """Reminder text for a silent PR (maintainers are mostly English-speaking, so it stays English)."""
    who = " ".join(f"@{p}" for p in dict.fromkeys(people)) or "there"
    return f"Hi {who}, gentle ping on this one. Is there anything you'd like me to change? Happy to rebase or adjust if needed."


def main():
    if not ME:
        return  # PR tracking is off
    now = datetime.now(timezone.utc)
    prs = gh("search", "prs", "--author", ME, "--state", "open", "--json", "repository,number,title,url", "--limit", "100")
    waiting, silent, errors = [], [], []
    for p in prs:
        repo = p["repository"]["nameWithOwner"]
        try:
            ev = events(repo, p["number"])
            when, who, kind = ev[-1]
        except Exception as e:
            errors.append(f"{repo}#{p['number']}: {e}")
            continue
        days = (now - datetime.fromisoformat(when.replace("Z", "+00:00"))).days
        line = f"{repo}#{p['number']} {p['title'][:70]} ({days} {T('gün önce', 'days ago')}, {p['url']})"
        if kind == "approve":
            waiting.append(f"{APPROVED}, {T('merge bekliyor', 'waiting for merge')}: {who} {T('onayladı', 'approved')}, {line}")
        elif who.lower() != ME.lower():
            waiting.append(f"{WAITING}: {who} {T('yazdı', 'wrote a')} {kind}, {line}")
        elif days > SILENT_DAYS:
            silent.append(f"{T('Sessiz: son söz senin', 'Silent: you had the last word')}, {line}")
            if "--taslak" in sys.argv:
                silent[-1] += T("\n  Taslak (gönderilmedi): ", "\n  Draft (not sent): ") + \
                    draft([w for _, w, _ in ev if w.lower() != ME.lower()])
    for line in waiting + silent:
        print(line)
    for e in errors:
        print(T("HATA:", "ERROR:"), e)
    print(T(f"{len(prs)} açık PR: {len(waiting)} cevap bekliyor, {len(silent)} {SILENT_DAYS} günden uzun sessiz",
            f"{len(prs)} open PRs: {len(waiting)} awaiting reply, {len(silent)} silent for over {SILENT_DAYS} days"))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
