"""Shift list: hours per person and uncovered days for one week, counted from the notes file, not by the model.

File: NOTES/vardiyalar.md (or shifts.md), one shift per line: `2026-11-20 | Ali | 07:00-15:00 | note`.
A shift past midnight (22:00-06:00) counts into the next day. Lines that don't match are skipped.
  python -I pentarch.py vardiya [YYYY-MM-DD]   week holding that day (default: this week)
"""
import datetime as dt
import re

import alacak
from config import NOTES, T

SATIR = re.compile(r"^\s*[-*]?\s*(\d{4}-\d{2}-\d{2})\s*\|\s*([^|]+?)\s*\|\s*(\d{1,2})[:.](\d{2})\s*-\s*(\d{1,2})[:.](\d{2})")
GUNLER = (T("Pzt", "Mon"), T("Sal", "Tue"), T("Çar", "Wed"), T("Per", "Thu"), T("Cum", "Fri"), T("Cmt", "Sat"), T("Paz", "Sun"))


def dosya():
    for ad in ("vardiyalar.md", "shifts.md"):
        if (NOTES / ad).exists():
            return NOTES / ad
    return None


def ozet(metin, gun):
    """Text summary for the Monday-to-Sunday week holding `gun`."""
    pzt = gun - dt.timedelta(days=gun.weekday())
    saat, dolu, cakisma, onceki = {}, set(), [], {}
    for line in metin.splitlines():
        m = SATIR.match(line)
        if not m:
            continue
        try:
            d = dt.date.fromisoformat(m[1])
        except ValueError:
            continue
        if not pzt <= d < pzt + dt.timedelta(days=7):
            continue
        bas, bit = int(m[3]) * 60 + int(m[4]), int(m[5]) * 60 + int(m[6])
        if bit <= bas:
            bit += 24 * 60
        kisi = m[2]
        saat[kisi] = saat.get(kisi, 0) + bit - bas
        dolu.add(d)
        for b, e in onceki.get((d, kisi.lower()), []):
            if bas < e and b < bit:
                cakisma.append(f"{d} {kisi}")
        onceki.setdefault((d, kisi.lower()), []).append((bas, bit))
    bas_satir = T(f"Hafta {pzt} – {pzt + dt.timedelta(days=6)}", f"Week {pzt} – {pzt + dt.timedelta(days=6)}")
    if not saat:
        return bas_satir + T(": bu hafta vardiya yok.", ": no shifts this week.")
    out = [bas_satir] + [f"- {k}: {v // 60} {T('sa', 'h')}{f' {v % 60} {T(chr(100) + chr(107), chr(109) + chr(105) + chr(110))}' if v % 60 else ''}" for k, v in sorted(saat.items())]
    bos = [f"{GUNLER[i]} {pzt + dt.timedelta(days=i)}" for i in range(7) if pzt + dt.timedelta(days=i) not in dolu]
    if bos:
        out.append(T("Kimsenin olmadığı gün: ", "Nobody on: ") + ", ".join(bos))
    if cakisma:
        out.append(T("Aynı kişiye çakışan vardiya: ", "Overlapping shifts for one person: ") + ", ".join(cakisma))
    return "\n".join(out)


def cli(args):
    f = dosya()
    if not f:
        return T(f"Vardiya dosyası yok. {NOTES / 'vardiyalar.md'} içine satır satır yaz: 2026-11-20 | Ali | 07:00-15:00",
                 f"No shift file. Write lines into {NOTES / 'shifts.md'}: 2026-11-20 | Ali | 07:00-15:00")
    try:
        gun = dt.date.fromisoformat(args[0]) if args else dt.date.today()
    except ValueError:
        return T("Tarih YYYY-AA-GG olmalı.", "Date must be YYYY-MM-DD.")
    try:
        return ozet(alacak.oku(f), gun)
    except UnicodeDecodeError:
        return T(f"{f} okunamadı: UTF-8 olarak kaydet.", f"Could not read {f}: save it as UTF-8.")
