"""Pre-send reply audit: cheap regex checks on the chat reply before it goes out.

- tarih_kontrol: years far from today, past or invalid dd.mm.yyyy dates, "12k"-style amounts without currency/period.
- okuma_dogrula: numbers and "round/level/day N" labels in the reply that are nowhere in the owner's message.
- ozet_kontrol: optional, config audit.summary_fields ({name: regex}) must all appear in a long reply whose source
  matches audit.summary_trigger. Empty = off.
Only a suspect year/date changes the reply (one warning line); everything else goes to the run log as
`denetim tarih/okuma/özet: ...`. A check that fails never blocks the reply.

Counter: python -I denetim.py [days=7]   counts those log lines by kind and pattern.
"""
import collections
import re
import sys
from datetime import date, datetime, timedelta

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # python -I leaves the script's folder off the path
from config import C, HOME, T

RUN_LOG = HOME / "pentarch.log"
ETIKET = re.compile(r"\b(track|round|tur|kategori|category|aşama|stage|gün|day|sezon|season|seviye|level)\s*(\d+)\b")
UYARI_BASI = ("yıl ", "tarih ", "geçersiz tarih", "year ", "date ", "invalid date")


def tarih_kontrol(metin, bugun=None):
    bugun = bugun or date.today()
    sorun = []
    for m in re.finditer(r"\b(19|20)\d\d\b", metin):
        y = int(m.group())
        if y < bugun.year - 1 or y > bugun.year + 2:
            yer = metin[max(0, m.start() - 25):m.end() + 15]
            sorun.append(T(f"yıl {y} bugünden ({bugun.year}) uzak: ...{yer}...",
                           f"year {y} is far from today ({bugun.year}): ...{yer}..."))
    for m in re.finditer(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b", metin):
        try:
            d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            if d < bugun:
                sorun.append(T(f"tarih {m.group()} geçmiş ({(bugun - d).days} gün önce)",
                               f"date {m.group()} is in the past ({(bugun - d).days} days ago)"))
        except ValueError:
            sorun.append(T(f"geçersiz tarih {m.group()}", f"invalid date {m.group()}"))
    for m in re.finditer(r"\b(\d[\d.,]*)\s*(bin|milyon|thousand|million|k|K)\b", metin):
        sorun.append(T(f"tutar '{m.group()}': para birimi ve dönem (aylık/yıllık) yazılı mı bak",
                       f"amount '{m.group()}': check currency and period (monthly/yearly) are stated"))
    return sorun


def okuma_dogrula(kaynak, taslak):
    k, t = kaynak.casefold(), taslak.casefold()
    fark = []
    for m in ETIKET.finditer(t):
        if not re.search(rf"\b{m.group(1)}\s*{m.group(2)}\b|\b{m.group(2)}\.?\s*{m.group(1)}\b", k):
            fark.append(T(f"'{m.group()}' kaynakta yok", f"'{m.group()}' not in the source"))
    kn = set(re.findall(r"\d+", k))
    for n in sorted(set(re.findall(r"\d+", t)) - kn):
        if not any(n in f for f in fark):
            fark.append(T(f"sayı {n} kaynakta yok", f"number {n} not in the source"))
    return fark


def ozet_kontrol(kaynak, taslak):
    a = C.get("audit") or {}
    alanlar, tetik = a.get("summary_fields") or {}, a.get("summary_trigger") or ""
    if not alanlar or not tetik or len(taslak) <= 200 or not re.search(tetik, kaynak, re.I):
        return []
    return [ad for ad, r in alanlar.items() if not re.search(r, taslak, re.I)]


def cevap_denetle(reply, texts, log=print):
    """Runs the three checks; returns the reply, with one warning line added only for a suspect year/date."""
    if not reply or not (C.get("audit") or {}).get("enabled", True) or reply.startswith(("Hata:", "Error:", "Durdurdum", "Stopped")):
        return reply
    kaynak = "\n".join(texts)
    uyar = []
    try:
        if t := tarih_kontrol(reply):
            log("denetim tarih: " + " | ".join(t)[:300])
            uyar = [s for s in t if s.startswith(UYARI_BASI)]
        if o := okuma_dogrula(kaynak, reply):
            log("denetim okuma: " + " | ".join(o)[:300])
        if e := ozet_kontrol(kaynak, reply):
            log("denetim özet: " + T("eksik: ", "missing: ") + ", ".join(e)[:200])
    except Exception as e:  # a broken check (bad regex in config) never stops the reply
        log(f"denetim olmadı: {e!r}")
    if uyar:
        reply = reply.rstrip() + "\n" + T("(Dikkat, tarih/yıl şüpheli: ", "(Careful, suspect date/year: ") + uyar[0][:120] + ")"
    return reply


def say(gun=7, log_file=RUN_LOG):
    """Audit log lines of the last `gun` days by kind, the 8 most common patterns and repeated unsourced numbers."""
    sinir = datetime.now() - timedelta(days=gun)
    tur, kural, sayilar = collections.Counter(), collections.Counter(), collections.Counter()
    try:
        satirlar = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        satirlar = []
    for s in satirlar:
        m = re.match(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) denetim (tarih|okuma|özet): (.*)", s)
        if not m or datetime.strptime(m[1], "%Y-%m-%d %H:%M:%S") < sinir:
            continue
        tur[m[2]] += 1
        for p in m[3].split(" | "):
            kural[(m[2], re.sub(r"\d+", "N", p.strip())[:60])] += 1
            if m[2] == "okuma":
                for n in re.findall(r"(?:sayı|number) (\d+) (?:kaynakta yok|not in the source)", p):
                    sayilar[n] += 1
    out = [T(f"Son {gun} gün: {sum(tur.values())} denetim kaydı", f"Last {gun} days: {sum(tur.values())} audit entries")
           + (" (" + ", ".join(f"{a} {b}" for a, b in tur.items()) + ")" if tur else "")]
    out += [f"  {n:3d}  {t}: {k}" for (t, k), n in kural.most_common(8)]
    tekrar = [f"{n} ({c}x)" for n, c in sayilar.most_common(5) if c > 1]
    if tekrar:
        out.append(T("Tekrar eden 'kaynakta yok' sayıları (gürültü adayı): ", "Repeated unsourced numbers (likely noise): ")
                   + ", ".join(tekrar))
    return "\n".join(out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(say(int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 7))
