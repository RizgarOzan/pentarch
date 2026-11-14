"""Counts the messages the assistant sent the owner in the last N hours and finds near-duplicate pairs: a measure for
"you write too much, you keep repeating yourself". Similarity: Jaccard >= 0.5 on the sets of 4+ letter words.

Usage: python -I mesaj_denetim.py [hours=24]
"""
import re
import sys
from collections import Counter
from datetime import datetime, timedelta

from config import NAME, T
from tg import LOG_FILE

LINE = re.compile(rf"^(\d{{4}}-\d\d-\d\d \d\d:\d\d) \| {re.escape(NAME)}([^:]*): (.*)$")
# fixed system texts (busy notice, pause/resume): their repeats are not repeated content
SABLON = ("Önceki iş sürüyor", "Koşular ", "Her şey durdu", "Zaten çalışıyordu",
          "Still on the previous job", "Runs ", "Everything stopped", "It was already running")


def mesajlar(saat, log_file=None):
    """[(time, source, text)] of the assistant's lines in the last `saat` hours."""
    since = datetime.now() - timedelta(hours=saat)
    out = []
    try:
        satirlar = (log_file or LOG_FILE).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return out
    for line in satirlar:
        m = LINE.match(line)
        if m and datetime.strptime(m.group(1), "%Y-%m-%d %H:%M") >= since:
            out.append((m.group(1), m.group(2).strip(" ()") or "telegram", m.group(3)))
    return out


def bag(t):
    return set(re.findall(r"[^\W\d_]{4,}", t.lower()))


def tekrarlar(msgs):
    """[(i, j)]: each message paired with the first later one that looks like a repeat."""
    bags = [bag(t) for _, _, t in msgs]
    out = []
    for i in range(len(msgs)):
        for j in range(i + 1, len(msgs)):
            a, b = bags[i], bags[j]
            if a and b and len(a & b) / len(a | b) >= 0.5:
                out.append((i, j))
                break
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    hours = next((int(a) for a in sys.argv[1:] if a.isdigit()), 24)
    msgs = mesajlar(hours)
    sablon = [m for m in msgs if m[2].startswith(SABLON)]
    msgs = [m for m in msgs if not m[2].startswith(SABLON)]
    print(T(f"Son {hours} saat: {len(msgs) + len(sablon)} {NAME} mesajı ({len(sablon)} şablon, tekrar sayılmadı)",
            f"Last {hours} hours: {len(msgs) + len(sablon)} {NAME} messages ({len(sablon)} fixed notices, not counted as repeats)"))
    print(T("Kaynak: ", "Source: ") + ", ".join(f"{k} {v}" for k, v in Counter(s for _, s, _ in msgs).most_common()))
    print(T("Saat: ", "Hour: ") + ", ".join(f"{k} {v}" for k, v in sorted(Counter(t[11:13] for t, _, _ in msgs).items())))
    dup = tekrarlar(msgs)
    for i, j in dup:
        print(T("TEKRAR", "REPEAT") + f" {msgs[i][0][5:]} / {msgs[j][0][5:]}: {msgs[i][2][:70]}")
    print(T(f"Tekrara benzeyen mesaj: {len(dup)}", f"Messages that look like repeats: {len(dup)}"))


if __name__ == "__main__":
    main()
