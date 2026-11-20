"""Expense ledger in plain words, for a shop owner: what you spent, this month's total, no model.

File: NOTES/giderler.md (or expenses.md), one line each: `2026-11-20 | Un | 1200 | toptan`.
In the chat:  gider ekle un 1200 [not]   (expense add flour 1200 [note], quotes for a two-word name)
              gider  (expenses)          this month and last month, the biggest names
Lines that don't match are skipped and reported. Reuses alacak.py's reader, writer and number parsing.
"""
import datetime as dt
import re

import alacak
from config import NOTES, T

KOMUT = re.compile(r"\s*/?(?:gider|giderler|expenses?)(?:\s+(?:ekle|add)\s+(.+?))?\s*", re.I | re.S)


def dosya():
    for ad in ("giderler.md", "expenses.md"):
        if (NOTES / ad).exists():
            return NOTES / ad
    return None


def ekle(args, bugun=None):
    """gider ekle NAME AMOUNT [note...]; the date is today. Returns (message, ok)."""
    a = list(args)
    kullanim = T('Kullanım: gider ekle un 1200 [not]  (iki kelimeli isim tırnak içinde)', 'Usage: expense add flour 1200 [note]  (two-word names in quotes)')
    if len(a) < 2 or "|" in " ".join(a) or any(c in x for x in a for c in (chr(13), chr(10))) or len(a[1]) > 15:
        return kullanim, False
    ad, miktar, *not_ = a
    gun = (bugun or dt.date.today()).isoformat()
    satir = f"{gun} | {ad} | {miktar}" + (f" | {' '.join(not_)}" if not_ else "")
    if not (m := alacak.SATIR.match(satir)) or m[3] != ad:
        return kullanim, False
    try:
        alacak.tutar(m[4])
    except ValueError:
        return kullanim, False
    f = dosya() or NOTES / T("giderler.md", "expenses.md")
    f.parent.mkdir(parents=True, exist_ok=True)
    try:
        eski = alacak.oku(f) if f.exists() else ""
    except UnicodeDecodeError:
        return T("Dosya okunamadı: UTF-8 olarak kaydet.", "Could not read the file: save it as UTF-8."), False
    sonu = chr(13) + chr(10) if chr(13) + chr(10) in eski else chr(10)
    alacak.yaz(f, eski + ("" if not eski or eski.endswith(chr(10)) else sonu) + "- " + satir + sonu)
    return T(f"Eklendi: {satir}", f"Added: {satir}"), True


def ozet(metin, bugun):
    """This month's total with its biggest names, and last month's total to compare."""
    ay = lambda d: (d.year, d.month)
    onceki = (bugun.replace(day=1) - dt.timedelta(days=1))
    rows = alacak.kayitlar(metin)
    bu = [r for r in rows if ay(r[1]) == ay(bugun)]
    once = [r for r in rows if ay(r[1]) == ay(onceki)]
    if not bu and not once:
        return T("Bu ay ve geçen ay kayıtlı gider yok.", "No expenses recorded this month or last.")
    out = [T(f"Bu ay ({bugun:%Y-%m}): {alacak.para(sum(r[3] for r in bu))}", f"This month ({bugun:%Y-%m}): {alacak.para(sum(r[3] for r in bu))}")]
    toplam = {}
    for r in bu:
        toplam[alacak.kucuk(r[2])] = toplam.get(alacak.kucuk(r[2]), 0) + r[3]
    adlar = {alacak.kucuk(r[2]): r[2] for r in bu}
    out += [f"- {adlar[k]} {alacak.para(v)}" for k, v in sorted(toplam.items(), key=lambda x: -x[1])[:5]]
    out.append(T(f"Geçen ay ({onceki:%Y-%m}): {alacak.para(sum(r[3] for r in once))}", f"Last month ({onceki:%Y-%m}): {alacak.para(sum(r[3] for r in once))}"))
    return chr(10).join(out)


def cli(args=()):
    f = dosya()
    if not f:
        return T(f"Gider dosyası yok. Başlamak için: gider ekle un 1200  ({NOTES / 'giderler.md'} oluşur)",
                 f"No expense file yet. To start: expense add flour 1200  (creates {NOTES / 'expenses.md'})")
    try:
        metin = alacak.oku(f)
    except UnicodeDecodeError:
        return T(f"{f} okunamadı: UTF-8 olarak kaydet.", f"Could not read {f}: save it as UTF-8.")
    atla = alacak.atlanan(metin)
    uyari = (chr(10) + T(f"UYARI: {len(atla)} satır okunamadı, toplama girmedi:", f"WARNING: {len(atla)} line(s) could not be read and are not in the totals:")
             + chr(10) + chr(10).join(atla[:5])) if atla else ""
    return ozet(metin, dt.date.today()) + uyari


def komut(text):
    """Chat commands that need no model; None when the message isn't one."""
    if not (m := KOMUT.fullmatch(text)):
        return None
    if m.group(1) is None:
        return cli()
    return ekle([a or b for a, b in re.findall(r'"([^"]+)"|(\S+)', m.group(1))])[0]
