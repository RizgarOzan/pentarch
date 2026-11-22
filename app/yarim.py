"""Everything still open, in one list: the task queue, answers being waited for, reminders and the open-tasks section
of memory.md. The answer to "what is still pending?".

Usage: python -I yarim.py [--long]   (--long: don't cut the texts)
"""
import json
import re
import sys

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # python -I leaves the script's folder off the path
from config import HOME, T

OPEN_SECTION = ("Open tasks", "Açık işler")
KAPALI = re.compile(r"^[\d: -]*\s*(?:\w+ ){0,4}(?:bitti|tamamlandı|çözüldü|kapandı|done|finished|resolved|closed)\b", re.I)


def _load(name):
    try:
        return json.loads((HOME / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def acik_isler(sayfa):
    """(open lines, lines that read as already finished) from the open-tasks section of memory.md."""
    sec = re.search(r"\n## (?:" + "|".join(map(re.escape, OPEN_SECTION)) + r")[^\n]*\n(.*?)(?=\n## |\Z)", "\n" + sayfa, re.S)
    acik, kapali = [], []
    for line in (sec.group(1).splitlines() if sec else []):
        if line.startswith("- "):
            (kapali if KAPALI.search(line[2:]) else acik).append(line[2:])  # "... done" is a note, not open work
    return acik, kapali


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    cut = 10**6 if {"--long", "--uzun"} & set(sys.argv) else 110
    n = 0
    print(T("GÖREV KUYRUĞU", "TASK QUEUE"))
    for g in sorted(_load("gorevler.json"), key=lambda x: x.get("zaman", "")):
        is_metni = re.sub(r"\s+", " ", g.get("is", ""))  # not inside the f-string: a backslash there is a SyntaxError before Python 3.12
        print(f"  {g.get('zaman', '?')}  {is_metni[:cut]}")
        n += 1
    print(T("CEVAP BEKLEYEN", "WAITING FOR AN ANSWER"))
    for b in _load("bekleyen.json"):
        print(f"  {b.get('zaman', '?')}  {b.get('yer', '')}: {b.get('ne', '')[:cut]}")
        n += 1
    print(T("HATIRLATMA", "REMINDERS"))
    for h in _load("hatirlatmalar.json"):
        print(f"  {h.get('zaman', '?')}  {h.get('metin', '')[:cut]}")
        n += 1
    print(T("HAFIZADAKİ AÇIK İŞLER", "OPEN TASKS IN MEMORY"))
    try:
        acik, kapali = acik_isler((HOME / "memory.md").read_text(encoding="utf-8"))
    except OSError:
        acik, kapali = [], []
        print(T("  (hafıza okunamadı)", "  (memory.md unreadable)"))
    for body in acik:
        print("  " + (body if len(body) <= cut else body[:cut].rsplit(" ", 1)[0] + " ..."))
        n += 1
    print(T(f"Toplam {n} açık madde.", f"{n} open items in total.")
          + (T(f" ({len(kapali)} madde kapanmış görünüp atlandı)", f" ({len(kapali)} items look finished and were skipped)")
             if kapali else ""))


if __name__ == "__main__":
    main()
