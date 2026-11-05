"""Upcoming deadlines and things left hanging: the morning brief builds its suggestion from this instead of waiting to be asked.

No model, instant. Lists lines in the notes folder that mention a date in the next N days (2026-11-05, 5 Kasım,
5 November, November 5), tasks whose time has passed, and pending replies older than 24 hours.
    python -I hedef.py        # 7 days
    python -I hedef.py 14
"""
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import HOME, NOTES, T  # noqa: E402

AYLAR = ["ocak", "şubat", "mart", "nisan", "mayıs", "haziran", "temmuz", "ağustos", "eylül", "ekim", "kasım", "aralık"]
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]
NAMES = "|".join(AYLAR + MONTHS + [m[:3] for m in MONTHS if len(m) > 3] + ["sept"])
ISO = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")
DAY_MONTH = re.compile(r"\b(\d{1,2}) (" + NAMES + r")\b\.?(?:'\w+)?", re.I)
MONTH_DAY = re.compile(r"\b(" + NAMES + r")\.? (\d{1,2})(?:st|nd|rd|th)?\b", re.I)
SKIP = re.compile(r"^(updated|tarih|date|created):|^\s*\|?\s*20\d\d-\d\d-\d\d \d\d:\d\d")  # frontmatter, log tables


def month(name):
    name = name.lower()
    if name in AYLAR:
        return AYLAR.index(name) + 1
    return next(i + 1 for i, m in enumerate(MONTHS) if m.startswith(name[:3]))


def dates_in(line, today):
    for m in ISO.finditer(line):
        if line[max(0, m.start() - 1):m.start()] == "(":  # "(2026-10-31)" stamps the day it was written, not a deadline
            continue
        try:
            yield datetime(*map(int, m.groups())).date()
        except ValueError:
            pass
    pairs = [(d, n) for d, n in DAY_MONTH.findall(line)] + [(d, n) for n, d in MONTH_DAY.findall(line)]
    for d, n in pairs:
        try:
            yield datetime(today.year, month(n), int(d)).date()
        except ValueError:
            pass


def notes():
    if not NOTES.is_dir():
        return []
    return [p for p in NOTES.rglob("*.md") if not any(part.startswith(".") for part in p.relative_to(NOTES).parts)]


def upcoming(days):
    today = datetime.now().date()
    end = today + timedelta(days=days)
    hits = {}
    for page in notes():
        if page.stem.startswith("log"):
            continue
        for line in page.read_text(encoding="utf-8", errors="replace").splitlines():
            if SKIP.search(line) or ISO.match(line.strip(" -*|#")):  # a log line: starts with a date
                continue
            when = [d for d in dates_in(line, today) if today <= d <= end]
            if when:
                text = re.sub(r"\s+", " ", line.strip(" -*|#"))[:160]
                hits.setdefault((min(when), text), page.stem)
    return sorted(hits.items())


def overdue():
    out, now = [], datetime.now()
    tasks = json.loads((HOME / "gorevler.json").read_text(encoding="utf-8")) if (HOME / "gorevler.json").exists() else []
    for t in tasks:
        if datetime.strptime(t["zaman"], "%Y-%m-%d %H:%M") < now - timedelta(hours=1):
            out.append(T(f"vakti geçmiş görev ({t['zaman']}): ", f"overdue task ({t['zaman']}): ") + t["is"][:100])
    pending = json.loads((HOME / "bekleyen.json").read_text(encoding="utf-8")) if (HOME / "bekleyen.json").exists() else []
    for p in pending:
        stamp = p.get("zaman") or p.get("kayit") or ""
        try:
            if datetime.strptime(stamp[:16], "%Y-%m-%d %H:%M") < now - timedelta(hours=24):
                out.append((T(f"24 saati geçen bekleyen cevap ({stamp[:16]}): ", f"reply pending over 24 h ({stamp[:16]}): ")
                            + f"{p.get('yer', '')} {p.get('ne', '')}")[:160])
        except ValueError:
            pass
    return out


def main():
    if sys.argv[1:2] in (["-h"], ["--help"]):
        sys.exit(__doc__)
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    rows = upcoming(days)
    print(T(f"Önümüzdeki {days} gün:", f"Next {days} days:") if rows else
          T(f"Önümüzdeki {days} günde notlarda tarih yok.", f"No dates in the notes for the next {days} days."))
    for (day, text), page in rows[:25]:
        print(f"{day:%d.%m} [{page}] {text}")
    for line in overdue():
        print(line)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
