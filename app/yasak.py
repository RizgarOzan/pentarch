"""Pre-send ban check: does a message, recipient or target touch a topic the owner closed or a person/place they said
not to write to? Source: the Rules and Rejected sections of memory.md (the same text every chat turn gets).

Usage: python -I yasak.py "message text, recipient or server name"   (exit 1 = BANNED, 0 = clean)
"""
import re
import sys

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # python -I leaves the script's folder off the path
from config import NAME, OWNER, T

AD = r"[A-ZÇĞİÖŞÜ][\w.'’-]*(?: (?:[A-ZÇĞİÖŞÜ]|de |la |van |von )[\w.'’-]*)*"  # capitalised name, may span words
YAZMA = re.compile(r"mesaj atma|yazma|yazmayacaksın|ulaşma|iletişime geçme|"
                   r"don'?t (?:write|message|contact|dm|email|e-mail|post|reach)|never (?:write|message|contact|dm|email|post)|"
                   r"no (?:messages|contact|posts)", re.I)
TARIH = re.compile(r"^- (?:\d{4}-\d\d-\d\d(?: \d\d:\d\d)?: )?")


def _adlar(parca):
    """Proper names inside a phrase. The phrase's first word is skipped: it is capitalised as a sentence start."""
    rest = parca.split(" ", 1)[1] if " " in parca else ""
    out = []
    for a in re.findall(AD, rest):
        a = re.split(r"['’]", a)[0].strip(" .")
        if len(a) > 3 and a.casefold() not in (OWNER.casefold(), NAME.casefold()):
            out.append(a)
    return out


def terimler(kurallar):
    """term -> the memory line it came from. kurallar: text with '## Rules' / '## Rejected' style sections."""
    t, bolum = {}, ""
    for s in kurallar.splitlines():
        if s.startswith("## "):
            bolum = s[3:].strip().casefold()
            continue
        if not s.startswith("- "):
            continue
        govde = TARIH.sub("", s).strip()
        if bolum in ("rejected", "reddedilenler"):
            konu = re.split(r"[.(,:;]", govde, maxsplit=1)[0].strip()
            for parca in re.split(r"/| and | ve ", konu):
                parca = parca.strip()
                if len(parca) > 3:
                    t.setdefault(parca, s)
                    for a in _adlar(parca):
                        t.setdefault(a, s)
        elif bolum in ("rules", "kurallar") and YAZMA.search(govde):
            for a in _adlar(govde):
                t.setdefault(a, s)
    for k in list(t):  # "Acme (Discord server)" also matches as plain "Acme"
        k2 = re.sub(r"\s*\(.*", "", k).strip()
        if k2 and k2 != k:
            t.setdefault(k2, t[k])
    return t


def kontrol(metin, kurallar):
    """[(term, memory line)] that the text touches."""
    m = metin.casefold()
    return [(k, v) for k, v in terimler(kurallar).items() if k.casefold() in m]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    metin = " ".join(sys.argv[1:])
    if not metin.strip():
        print(__doc__)
        return 2
    from pentarch import reddedilenler
    bulgu = kontrol(metin, reddedilenler())
    if not bulgu:
        print(T("TEMİZ: yasak listesinde eşleşme yok", "CLEAN: nothing on the ban list matches"))
        return 0
    for k, v in bulgu:
        print(T("YASAK", "BANNED") + f": '{k}' -> {v[:140]}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
