"""Assignments and exams, counted from the notes file, not by the model.

File: NOTES/dersler.md (or study.md), one line each: `2026-12-05 | Calculus | midterm exam` or `2026-11-28 | Physics | lab report`.
A line starting `- [x]` is done and skipped. Lines that name an exam (sınav, vize, final, exam, midterm, quiz) get a
countdown in days. Lines that don't match are skipped.
  python -I pentarch.py ders     overdue, due this week, upcoming exams
"""
import datetime as dt
import re

import alacak
from config import NOTES, T

SATIR = re.compile(r"^\s*[-*]?\s*(\d{4}-\d{2}-\d{2})\s*\|\s*([^|]+?)\s*\|\s*(.+?)\s*$")
BITTI = re.compile(r"^\s*[-*]\s*\[x\]", re.I)
SINAV = re.compile(r"\b(sınav|sinav|vize|final|bütünleme|butunleme|exam|midterm|quiz|test)\b", re.I)


def dosya():
    for ad in ("dersler.md", "study.md"):
        if (NOTES / ad).exists():
            return NOTES / ad
    return None


def kayitlar(metin):
    out = []
    for line in metin.splitlines():
        if BITTI.match(line):
            continue
        m = SATIR.match(line)
        if not m:
            continue
        try:
            out.append((dt.date.fromisoformat(m[1]), m[2], m[3], bool(SINAV.search(m[3]))))
        except ValueError:
            continue
    return sorted(out)


def _satir(r, bugun):
    gun = (r[0] - bugun).days
    when = T("bugün", "today") if gun == 0 else T(f"{-gun} gün gecikti", f"{-gun} days late") if gun < 0 else T(f"{gun} gün kaldı", f"in {gun} days")
    return f"- {r[1]}: {r[2]} ({r[0]}, {when})"


def ozet(metin, bugun, gun=7, sinav_gun=30):
    """Overdue, due within `gun` days, and exams within `sinav_gun` days; '' when there is nothing to say."""
    rows = kayitlar(metin)
    gec = [r for r in rows if r[0] < bugun]
    yakin = [r for r in rows if bugun <= r[0] <= bugun + dt.timedelta(days=gun)]
    sinav = [r for r in rows if r[3] and bugun + dt.timedelta(days=gun) < r[0] <= bugun + dt.timedelta(days=sinav_gun)]
    parts = []
    for baslik, secim in ((T("Geciken", "Overdue"), gec), (T("Bu hafta", "This week"), yakin), (T("Yaklaşan sınavlar", "Upcoming exams"), sinav)):
        if secim:
            parts.append(baslik + ":")
            parts += [_satir(r, bugun) for r in secim]
    return "\n".join(parts)


def cli(args=()):
    f = dosya()
    if not f:
        return T(f"Ders dosyası yok. {NOTES / 'dersler.md'} içine satır satır yaz: 2026-12-05 | Calculus | vize sınavı",
                 f"No study file. Write lines into {NOTES / 'study.md'}: 2026-12-05 | Calculus | midterm exam")
    try:
        metin = alacak.oku(f)
    except UnicodeDecodeError:
        return T(f"{f} okunamadı: UTF-8 olarak kaydet.", f"Could not read {f}: save it as UTF-8.")
    return ozet(metin, dt.date.today()) or T("Yaklaşan ödev ya da sınav yok.", "No assignment or exam coming up.")


def rutin():
    """Daily routine (no model): the message only when something is overdue, due this week or an exam is near; '-' otherwise."""
    f = dosya()
    try:
        return (ozet(alacak.oku(f), dt.date.today()) if f else "") or "-"
    except UnicodeDecodeError:
        return T("Ders dosyası okunamadı: UTF-8 olarak kaydet.", "Could not read the study file: save it as UTF-8.")
