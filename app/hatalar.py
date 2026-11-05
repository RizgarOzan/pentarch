"""Counts error lines in <home>/pentarch.log from the last N hours, grouped by kind. Usage: hatalar.py [hours=24]"""
import collections
import datetime
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import HOME, T  # noqa: E402

LOG = HOME / "pentarch.log"
KEL = re.compile(r"hata|error|exception|traceback|olmadı|düştü|failed|timeout|zaman aşımı", re.I)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:2] in (["-h"], ["--help"]):
        sys.exit(__doc__)
    saat = float(sys.argv[1]) if len(sys.argv) > 1 else 24
    sinir = datetime.datetime.now() - datetime.timedelta(hours=saat)
    sayac, son = collections.Counter(), {}
    lines = LOG.read_text(encoding="utf-8", errors="replace").splitlines() if LOG.exists() else []
    for s in lines:
        m = re.match(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) (.*)", s)
        if not m or not KEL.search(m.group(2)):
            continue
        try:
            if datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S") < sinir:
                continue
        except ValueError:
            continue
        anahtar = re.sub(r"\d+", "N", m.group(2))[:60]
        sayac[anahtar] += 1
        son[anahtar] = m.group(1)[5:16]
    print(T(f"Son {saat:g} saat: {sum(sayac.values())} hata satırı, {len(sayac)} tür",
            f"Last {saat:g} hours: {sum(sayac.values())} error lines, {len(sayac)} kinds"))
    for k, n in sayac.most_common(8):
        print(f"{n:3d}x  {k}  ({T('son', 'last')} {son[k]})")


if __name__ == "__main__":
    main()
