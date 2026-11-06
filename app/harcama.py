"""Daily spend report: adds up the run lines ("koşu ...") in <home>/pentarch.log by kind, job and hour.

Usage: python -I harcama.py [YYYY-MM-DD] [--en N]
A task run is matched to the oldest unfinished "görev başlıyor" line (approximate when runs overlap).
A scheduled run is matched to the last "zamanlı iş: X" line before it.
(The core writes these log lines in Turkish; they are internal markers, not user-facing text.)
"""
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import HOME, T  # noqa: E402

LOG = HOME / "pentarch.log"
KAYIT = HOME / "magi" / "kayit.jsonl"  # councils record per-seat API token usage (no $ price: free tiers vary)
RUN = re.compile(r"^(\S+) (\d\d):\d\d:\d\d koşu (\S+?): .*?(\d+)k token, ([\d.]+)\$")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    if args[:1] in (["-h"], ["--help"]):
        sys.exit(__doc__)
    top = 5
    if "--en" in args:
        i = args.index("--en")
        top = int(args[i + 1])
        del args[i:i + 2]
    day = args[0] if args else date.today().isoformat()

    by_kind = defaultdict(lambda: [0, 0.0])
    by_hour = defaultdict(float)
    items = []
    started, job = [], "?"
    lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines() if LOG.exists() else []
    for line in lines:
        if not line.startswith(day):
            continue
        if " görev başlıyor: " in line:
            started.append(line.split(" görev başlıyor: ", 1)[1][:70])
            continue
        if " zamanlı iş: " in line:
            job = line.split(" zamanlı iş: ", 1)[1].strip()
            continue
        m = RUN.match(line)
        if not m:
            continue
        _, hour, kind, _tok, usd = m.groups()
        usd = float(usd)
        by_kind[kind][0] += 1
        by_kind[kind][1] += usd
        by_hour[hour] += usd
        if kind == "görev":
            label = started.pop(0) if started else T("(adı bulunamadı)", "(name not found)")
        elif kind == "otomatik":
            label = T(f"rutin {job}", f"routine {job}")
        else:
            label = kind
        items.append((usd, f"{line[11:16]} {label}"))

    total = sum(v[1] for v in by_kind.values())
    print(T(f"{day} toplam {total:.2f}$", f"{day} total {total:.2f}$"))
    for kind, (n, usd) in sorted(by_kind.items(), key=lambda kv: -kv[1][1]):
        print(T(f"  {kind}: {n} koşu, {usd:.2f}$", f"  {kind}: {n} runs, {usd:.2f}$"))
    if by_hour:
        h, usd = max(by_hour.items(), key=lambda kv: kv[1])
        print(T(f"En pahalı saat: {h}:00, {usd:.2f}$", f"Most expensive hour: {h}:00, {usd:.2f}$"))
    print(T(f"En pahalı {top} koşu:", f"Top {top} runs by cost:"))
    for usd, label in sorted(items, reverse=True)[:top]:
        print(f"  {usd:.2f}$  {label}")
    seats = defaultdict(int)
    for line in KAYIT.read_text(encoding="utf-8").splitlines() if KAYIT.exists() else []:
        k = json.loads(line) if line.strip() else {}
        if k.get("zaman", "").startswith(day):
            for seat, u in (k.get("kullanim") or {}).items():
                seats[seat] += u.get("prompt_tokens", 0) + u.get("completion_tokens", 0)
    if seats:
        print(T("Konsey API tokenleri: ", "Council API tokens: ") + ", ".join(f"{s} {n // 1000}k" for s, n in seats.items()))


if __name__ == "__main__":
    main()
