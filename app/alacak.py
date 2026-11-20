"""Money owed to you (and bills you owe), counted from the notes file, not by the model.

File: NOTES/alacaklar.md (or receivables.md), one line each: `2026-11-30 | Ahmet Kafe | 4500 | ekmek faturası`.
A line starting `- [x]` is paid and skipped; `borc`/`owe` as the first word (`borc 2026-12-01 | Un Toptan | 12000`)
marks a bill you must pay. Lines that don't match are skipped.
  python -I pentarch.py alacak     overdue, due this week, totals
  python -I pentarch.py alacak ekle 2026-12-01 "Mia" 500 [note]    add a line (`borc` before the date for a bill you owe)
  python -I pentarch.py alacak odendi Mia                          mark the open line with that name as paid
"""
import codecs
import datetime as dt
import re

from config import C, LANG_CODES, NOTES, T

SATIR = re.compile(r"^\s*[-*]?\s*(?:(borc|owe)\s+)?(\d{4}-\d{2}-\d{2})\s*\|\s*([^|]+?)\s*\|\s*(?:[$€£₺]\s*)?([\d.,]+)\s*(?:[$€£₺]|[A-Za-z]{2,4})?\s*(?:\|\s*(.*))?$", re.I)
ODENDI = re.compile(r"^\s*[-*]\s*\[x\]", re.I)


def dosya():
    for ad in ("alacaklar.md", "receivables.md"):
        if (NOTES / ad).exists():
            return NOTES / ad
    return None


def oku(f):
    """File text. A UTF-8 BOM (Notepad) is dropped, UTF-16 (PowerShell 5 redirection) is decoded, anything else unreadable is an error."""
    b = f.read_bytes()
    if b.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return b.decode("utf-16")
    return b.decode("utf-8-sig")


def yaz(f, metin):
    """Whole-file write through a temp file, so a crash leaves the old file; LF stays LF, CRLF stays CRLF."""
    cr, lf = chr(13), chr(10)
    if cr + lf in metin:
        metin = metin.replace(cr + lf, lf).replace(lf, cr + lf)
    f = f.resolve()  # a symlinked notes file stays a symlink
    gecici = f.with_name(f.name + ".tmp")
    gecici.write_bytes(metin.encode("utf-8"))
    gecici.replace(f)


def kucuk(s):
    """Lower-case that knows Turkish i/İ and ı/I."""
    return s.replace("İ", "i").replace("I", "ı").lower()


def tutar(s):
    """'4.500,50' / '4,500.50' / '4500' -> float; the last separator with 1-2 digits after it is the decimal point."""
    m = re.fullmatch(r"(.*?)[.,](\d{1,2})", s)
    whole, frac = (m[1], m[2]) if m else (s, "0")
    if not re.fullmatch(r"\d{1,3}(?:[.,]\d{3})*|\d+", whole or "x"):
        raise ValueError(s)
    return float(re.sub(r"[.,]", "", whole) + "." + frac)


def kayitlar(metin):
    out = []
    for line in metin.splitlines():
        if ODENDI.match(line):
            continue
        m = SATIR.match(line)
        if not m:
            continue
        try:
            out.append((bool(m[1]), dt.date.fromisoformat(m[2]), m[3], tutar(m[4]), (m[5] or "").strip()))
        except ValueError:
            continue
    return out


def atlanan(metin):
    """Lines that start like an entry (a date, or borc/owe + date) but could not be read: a silent skip would make the totals wrong."""
    bas = re.compile(r"^\s*[-*]?\s*(?:(?:borc|owe)\s+)?(?:\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.\d{4})\s*\|", re.I)
    ok = {m for m in (l for l in metin.splitlines() if not ODENDI.match(l) and SATIR.match(l))}
    return [l.strip() for l in metin.splitlines() if bas.match(l) and not ODENDI.match(l) and l not in ok]


def para(x):
    t = f"{x:,.2f}"
    if t.endswith(".00"):
        t = t[:-3]
    avrupa = T("tr", "en") == "tr" or LANG_CODES.get((C.get("reply_lang") or "").strip().lower()) in ("de", "es", "fr")
    return t.translate(str.maketrans(",.", ".,")) if avrupa else t  # 1.250,50 in Turkish/German, 1,250.50 in English


def ozet(metin, bugun, gun=7):
    """Overdue and due-within-`gun`-days lines for both directions; '' when there is nothing to say."""
    parts = []
    for borc, baslik_gec, baslik_yakin in ((False, T("Geciken alacak", "Overdue, owed to you"), T("Bu hafta vadesi gelen alacak", "Owed to you, due soon")),
                                           (True, T("Geciken borç", "Overdue bills"), T("Bu hafta ödenecek borç", "Bills due soon"))):
        rows = sorted((r for r in kayitlar(metin) if r[0] == borc), key=lambda r: r[1])
        for baslik, secim in ((baslik_gec, [r for r in rows if r[1] < bugun]),
                              (baslik_yakin, [r for r in rows if bugun <= r[1] <= bugun + dt.timedelta(days=gun)])):
            if secim:
                parts.append(f"{baslik} ({para(sum(r[3] for r in secim))}):")
                parts += [f"- {r[2]} {para(r[3])}, {r[1]}" + (f" ({(bugun - r[1]).days} {T('gün', 'days')})" if r[1] < bugun else "")
                          + (f" {r[4]}" if r[4] else "") for r in secim]
    return "\n".join(parts)


def ekle(args):
    """alacak ekle [borc] DATE NAME AMOUNT [note...]. Returns (message, ok)."""
    a = list(args)
    borc = bool(a) and a[0].lower() in ("borc", "owe")
    a = a[1:] if borc else a
    kullanim = T('Kullanım: alacak ekle [borc] 2026-12-01 "İsim" 500 [not]', 'Usage: receivables ekle [owe] 2026-12-01 "Name" 500 [note]')
    if len(a) < 3 or "|" in " ".join(a) or any(c in x for x in a for c in (chr(13), chr(10))) or len(a[2]) > 15:
        return kullanim, False
    gun, ad, miktar, *not_ = a
    satir = f"{'borc ' if borc else ''}{gun} | {ad} | {miktar}" + (f" | {' '.join(not_)}" if not_ else "")
    if not (m := SATIR.match(satir)) or m[3] != ad:
        return kullanim, False
    try:
        dt.date.fromisoformat(gun)
        tutar(m[4])
    except ValueError:
        return kullanim, False
    f = dosya() or NOTES / T("alacaklar.md", "receivables.md")
    f.parent.mkdir(parents=True, exist_ok=True)
    try:
        eski = oku(f) if f.exists() else ""
    except UnicodeDecodeError:
        return T("Dosya okunamadı: UTF-8 olarak kaydet.", "Could not read the file: save it as UTF-8."), False
    yeni_satir = chr(13) + chr(10) if chr(13) + chr(10) in eski else chr(10)
    yaz(f, eski + ("" if not eski or eski.endswith(chr(10)) else yeni_satir) + "- " + satir + yeni_satir)
    return T(f"Eklendi: {satir}", f"Added: {satir}"), True


def odendi(ad):
    """Marks the one open line whose name contains `ad` as paid. Returns (message, ok)."""
    f = dosya()
    if not f or not ad.strip():
        return T("Alacak dosyası ya da isim yok.", "No receivables file or no name."), False
    try:
        satirlar = oku(f)
    except UnicodeDecodeError:
        return T("Dosya okunamadı: UTF-8 olarak kaydet.", "Could not read the file: save it as UTF-8."), False
    ayirac = chr(13) + chr(10) if chr(13) + chr(10) in satirlar else chr(10)  # the file keeps its own line ending
    satirlar = satirlar.replace(chr(13) + chr(10), chr(10)).split(chr(10))
    aranan = kucuk(ad.strip())
    idx = [i for i, l in enumerate(satirlar) if not ODENDI.match(l) and (m := SATIR.match(l)) and aranan in kucuk(m[3])]
    tam = [i for i in idx if kucuk(SATIR.match(satirlar[i])[3]) == aranan]
    if len(tam) == 1:  # "Mia" must be payable while "Mia Cafe" is still open
        idx = tam
    if not idx:
        return T(f"Açık satır bulunamadı: {ad}", f"No open line found for: {ad}"), False
    if len(idx) > 1:
        return T(f"{len(idx)} açık satır var, ismi daha net yaz:", f"{len(idx)} open lines match, be more specific:") + chr(10) + chr(10).join(satirlar[i].strip() for i in idx[:5]), False
    satirlar[idx[0]] = "- [x] " + re.sub(r"^\s*[-*]?\s*", "", satirlar[idx[0]])
    yaz(f, ayirac.join(satirlar))
    return T(f"Ödendi olarak işaretlendi: {satirlar[idx[0]][6:]}", f"Marked as paid: {satirlar[idx[0]][6:]}"), True


def cli(args=()):
    f = dosya()
    if not f:
        return T(f"Alacak dosyası yok. {NOTES / 'alacaklar.md'} içine satır satır yaz: 2026-11-30 | Ahmet Kafe | 4500 | not",
                 f"No receivables file. Write lines into {NOTES / 'receivables.md'}: 2026-11-30 | Ahmet Kafe | 4500 | note")
    try:
        metin = oku(f)
    except UnicodeDecodeError:
        return T(f"{f} okunamadı: UTF-8 (ya da UTF-16) olarak kaydet.", f"Could not read {f}: save it as UTF-8 (or UTF-16).")
    rows = kayitlar(metin)
    toplam = sum(r[3] for r in rows if not r[0])
    atla = atlanan(metin)
    uyari = ("\n" + T(f"UYARI: {len(atla)} satır okunamadı, toplama girmedi:", f"WARNING: {len(atla)} line(s) could not be read and are not in the totals:")
             + "\n" + "\n".join(atla[:5])) if atla else ""
    return (ozet(metin, dt.date.today()) or T("Vadesi gelen ya da geciken bir şey yok.", "Nothing overdue or due this week.")) + \
        "\n" + T(f"Açık alacak toplamı: {para(toplam)}", f"Total still owed to you: {para(toplam)}") + uyari


def rutin():
    """Weekly routine (no model): the message only when something is overdue or due; '-' otherwise."""
    f = dosya()
    try:
        return (ozet(oku(f), dt.date.today()) if f else "") or "-"
    except UnicodeDecodeError:
        return T("Alacak dosyası okunamadı: UTF-8 olarak kaydet.", "Could not read the receivables file: save it as UTF-8.")
