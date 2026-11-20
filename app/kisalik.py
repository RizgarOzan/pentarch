"""Measures how long the assistant's messages to the owner were in the last N hours and lists the ones over a limit.

Usage: python -I kisalik.py [hours=24] [limit=50]
"""
import sys

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # python -I leaves the script's folder off the path
from config import NAME, T
from mesaj_denetim import mesajlar


def olc(msgs, sinir):
    """(count, median words, longest, [(words, time, text)] over the limit, longest first)."""
    n = sorted(len(t.split()) for _, _, t in msgs)
    uzun = sorted(((len(t.split()), z, t) for z, _, t in msgs if len(t.split()) > sinir), key=lambda x: -x[0])
    return len(n), n[len(n) // 2] if n else 0, n[-1] if n else 0, uzun


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    saat = float(sys.argv[1]) if len(sys.argv) > 1 else 24
    sinir = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    sayi, orta, enuzun, uzun = olc(mesajlar(saat), sinir)
    if not sayi:
        print(T("mesaj yok", "no messages"))
        return
    print(T(f"Son {saat:g} saat: {sayi} {NAME} satırı, ortanca {orta} kelime, en uzun {enuzun}, {sinir} üstü {len(uzun)} (%{100 * len(uzun) // sayi})",
            f"Last {saat:g} hours: {sayi} {NAME} lines, median {orta} words, longest {enuzun}, over {sinir}: {len(uzun)} ({100 * len(uzun) // sayi}%)"))
    for c, z, s in uzun[:5]:
        print(f"  {c} {T('kelime', 'words')} {z[5:]} {s[:70]}")


if __name__ == "__main__":
    main()
