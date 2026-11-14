"""Checks a quote or claim against a file line ("see line 70 of the README"): prints the line with 2 lines of context
either side and says whether the phrase is on that line, nearby (line number drifted) or absent.

Usage: python -I satir_dogrula.py file line "phrase"   (exit 1 = not on that line)
"""
import sys
from pathlib import Path

from config import T


def dogrula(satirlar, n, ifade):
    """(verdict, context lines). verdict: "tam" on the line, "yakin" within 2 lines, "yok" elsewhere, None bad number."""
    if not 1 <= n <= len(satirlar):
        return None, []
    ifade = ifade.casefold()
    lo, hi = max(1, n - 2), min(len(satirlar), n + 2)
    baglam = [f"{'>' if i == n else ' '}{i}: {satirlar[i - 1][:200]}" for i in range(lo, hi + 1)]
    if ifade in satirlar[n - 1].casefold():
        return "tam", baglam
    return ("yakin" if any(ifade in satirlar[i - 1].casefold() for i in range(lo, hi + 1)) else "yok"), baglam


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 4 or not sys.argv[2].isdigit():
        print(__doc__)
        return 2
    satirlar = Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace").splitlines()
    n = int(sys.argv[2])
    sonuc, baglam = dogrula(satirlar, n, " ".join(sys.argv[3:]))
    if sonuc is None:
        print(T(f"dosyada {len(satirlar)} satır var, {n} yok", f"the file has {len(satirlar)} lines, not {n}"))
        return 1
    print("\n".join(baglam))
    print({"tam": T("EŞLEŞTİ (o satırda)", "MATCH (on that line)"),
           "yakin": T("YAKIN (±2 satırda, satır numarası kaymış)", "NEAR (within 2 lines, the line number drifted)"),
           "yok": T("YOK: ifade bu satırlarda geçmiyor", "ABSENT: the phrase is not on these lines")}[sonuc])
    return 0 if sonuc == "tam" else 1


if __name__ == "__main__":
    sys.exit(main())
