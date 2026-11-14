"""Contact ledger: who was told or asked what, on the owner's behalf, across sessions and channels.
Look before writing to someone (`goster`), record after sending or after reading their answer (`yaz`). A new session
does not see what an old one already asked, so it asked answered questions again. The ledger does not replace
reading the conversation itself in its channel.

Usage:
  python -I kisi.py goster "name"                          # every entry for that person, oldest first
  python -I kisi.py yaz "name" "channel" giden|gelen "gist"  # giden = sent, gelen = received; what was asked/said
  python -I kisi.py liste                                  # known people and their last contact
"""
import json
import sys
from datetime import datetime

from config import HOME, T

LEDGER = HOME / "kisiler.jsonl"
YON = {"giden": "giden", "out": "giden", "sent": "giden", "gelen": "gelen", "in": "gelen", "received": "gelen"}


def _k(s):
    return s.casefold().replace("i̇", "i").replace("ı", "i").strip()  # "ACME" = "Acme" = "acme", Turkish dotless i too


def kayitlar():
    out = []
    try:
        satirlar = LEDGER.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for s in satirlar:
        try:
            out.append(json.loads(s))
        except ValueError:
            pass
    return out


def goster(ad):
    k = _k(ad)
    bulunan = [r for r in kayitlar() if k and (k in _k(r["kisi"]) or _k(r["kisi"]) in k)]
    if not bulunan:
        return T(f"'{ad}' için kayıt yok. Yine de kanaldaki konuşmayı baştan oku.",
                 f"No entries for '{ad}'. Still read the conversation in its channel from the start.")
    return "\n".join(f"{r['zaman']} | {r['kisi']} | {r['kanal']} | {r['yon']}: {r['ozet']}" for r in bulunan)


def yaz(ad, kanal, yon, ozet):
    if yon not in YON:
        raise SystemExit(T("yön 'giden' ya da 'gelen' olmalı", "direction must be 'giden' (sent) or 'gelen' (received)"))
    r = {"zaman": datetime.now().strftime("%Y-%m-%d %H:%M"), "kisi": ad.strip(), "kanal": kanal.strip(),
         "yon": YON[yon], "ozet": " ".join(ozet.split())}
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return T("yazıldı", "recorded")


def liste():
    son = {}
    for r in kayitlar():
        son[_k(r["kisi"])] = r
    return "\n".join(f"{r['kisi']} ({r['kanal']}): {T('son', 'last')} {r['zaman']}" for r in son.values()) \
        or T("defter boş", "ledger is empty")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    if a[:1] == ["goster"] and len(a) == 2:
        print(goster(a[1]))
    elif a[:1] == ["yaz"] and len(a) == 5:
        print(yaz(*a[1:]))
    elif a[:1] == ["liste"]:
        print(liste())
    else:
        print(__doc__)
        sys.exit(2)
