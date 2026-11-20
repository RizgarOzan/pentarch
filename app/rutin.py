"""Routines: a prompt the owner wants run on a clock, like the built-in morning brief.

    pentarch.py rutin ekle <name> <when> "<what to do>"
    pentarch.py rutin hatirlat <name> <when> "<text>"   (the text itself goes out on time, no AI run)
      when: 08:30 (every day) | 09:00,21:00 (twice a day) | mon,fri@08:30 or pzt,cum@08:30 (those days) | 1,15@09:00 (those days of the month;
            31 means the last day) | 20@09:00 jan,apr,jul,oct (only those months: quarterly, yearly)
            | 90m or 90dk (every 90 min, 09:00-23:00)
            | 90m@07:00-01:00 (every 90 min inside that window; it may cross midnight)
    pentarch.py rutin liste | dur <name> | devam <name> | sil <name>

A responsibility chases a goal until it is done; a routine just repeats. They run read-only on the fast model, like
the built-in jobs: a change or an outward step comes back as a Yes/No proposal, never done on its own.
Data: <home>/rutinler.json. No model call happens here.
"""
import json
import re

from config import HOME, T

DOSYA = HOME / "rutinler.json"
AD = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
GUN = {"pzt": 0, "mon": 0, "sal": 1, "tue": 1, "çar": 2, "car": 2, "wed": 2, "per": 3, "thu": 3, "cum": 4, "fri": 4,
       "cmt": 5, "sat": 5, "paz": 6, "sun": 6,
       # Portuguese, Spanish, German, French (first three letters, accents dropped)
       "seg": 0, "lun": 0, "ter": 1, "mar": 1, "die": 1, "qua": 2, "mie": 2, "mit": 2, "mer": 2, "qui": 3, "jue": 3,
       "don": 3, "jeu": 3, "sex": 4, "vie": 4, "fre": 4, "ven": 4, "sab": 5, "sam": 5, "dom": 6, "son": 6, "dim": 6}
AY = {a: i % 12 + 1 for i, a in enumerate(
    "jan feb mar apr may jun jul aug sep oct nov dec oca şub mar nis may haz tem ağu eyl eki kas ara".split())}
AKSAN = str.maketrans("áâãàéêíóôõúüç", "aaaaeeiooouuc")
HARF = str.maketrans("çğıöşüâîûéèáàíóúñ ", "cgiosuaiueeaaioun-")  # "yüzme" -> "yuzme", "ilaç saati" -> "ilac-saati"


def adla(ad):
    return ad.strip().replace("İ", "i").replace("I", "ı").lower().translate(HARF)


def oku():
    try:
        return json.loads(DOSYA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _yaz(items):
    DOSYA.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def gun(g):
    """Day name -> 0-6. Turkish pazartesi/cumartesi start like pazar/cuma (Sunday/Friday), so they are checked whole."""
    g = g.strip().translate(AKSAN)
    return 0 if g.startswith("pazart") else 5 if g.startswith("cumart") else GUN[g[:3]]


def zaman(s):
    """'08:30' / 'mon,fri@08:30' / '20@09:00 jan,jul' / '90m' -> the fields pentarch.due() reads."""
    s = re.sub(r"\s*,\s*", ",", s.strip().lower())  # "mon, fri@08:30"
    s, _, aylar = s.partition(" ")
    if aylar.strip():
        try:
            ay = sorted({int(a) if a.strip().isdigit() else AY[a.strip()[:3]] for a in aylar.split(",")})
        except KeyError as e:
            raise ValueError(T(f"ay anlaşılmadı: {e.args[0]}", f"unknown month: {e.args[0]}")) from None
        if not 1 <= ay[0] <= ay[-1] <= 12:
            raise ValueError(T("ay 1-12 olmalı", "the month must be 1-12"))
        return {**zaman(s), "month": ay}
    hhmm = r"([01]?\d|2[0-3]):([0-5]\d)"
    if m := re.fullmatch(rf"(\d+)\s*(?:dk|m|min)(?:@{hhmm}-{hhmm})?", s):
        if not 15 <= int(m.group(1)) <= 1440:
            raise ValueError(T("aralık 15-1440 dakika olmalı", "the interval must be 15-1440 minutes"))
        g = m.groups()
        win = [f"{int(g[1]):02d}:{g[2]}", f"{int(g[3]):02d}:{g[4]}"] if g[1] else ["09:00", "23:00"]
        if win[0] == win[1]:
            raise ValueError(T("pencerenin başı ve sonu aynı olamaz", "the window can't start and end at the same time"))
        return {"every": int(m.group(1)), "between": win}
    gunler, _, hm = s.rpartition("@")
    saatler = [re.fullmatch(hhmm, h) for h in hm.split(",")]
    if not all(saatler):
        raise ValueError(T(f"zaman anlaşılmadı: {s} (08:30, 09:00,21:00, pzt,cum@08:30, 1,15@09:00, '20@09:00 oca,tem', 90dk ya da 90dk@07:00-01:00)",
                           f"can't read the time: {s} (08:30, 09:00,21:00, mon,fri@08:30, 1,15@09:00, '20@09:00 jan,jul', 90m or 90m@07:00-01:00)"))
    saatler = sorted({f"{int(m.group(1)):02d}:{m.group(2)}" for m in saatler})
    out: dict = {"at": saatler[0], **({"ats": saatler} if len(saatler) > 1 else {})}
    if re.fullmatch(r"\d{1,2}(,\d{1,2})*", gunler):  # "1,15@09:00": days of the month
        out["monthday"] = sorted({int(g) for g in gunler.split(",")})
        if not 1 <= out["monthday"][0] <= out["monthday"][-1] <= 31:
            raise ValueError(T("ayın günü 1-31 olmalı", "the day of the month must be 1-31"))
    elif gunler:
        try:
            out["weekday"] = sorted({gun(g) for g in gunler.split(",")})
        except KeyError as e:
            raise ValueError(T(f"gün anlaşılmadı: {e.args[0]}", f"unknown day: {e.args[0]}")) from None
    return out


def ekle(ad, ne_zaman, is_, hatirlat=False):
    """hatirlat=True: the text itself is sent at that time, no model run (pills, a call); never dropped as a repeat."""
    ad = adla(ad)
    if not AD.match(ad):
        raise ValueError(T("ad: küçük harf, rakam, tire (en çok 40)", "name: lowercase letters, digits, dashes (40 max)"))
    if not is_.strip() or len(is_) > 1500:
        raise ValueError(T("iş metni 1-1500 karakter olmalı", "the job text must be 1-1500 characters"))
    r = {"ad": ad, "zaman": ne_zaman.strip(), **zaman(ne_zaman), "is": is_.strip(), "durum": "aktif",
         **({"tur": "hatirlat"} if hatirlat else {})}
    _yaz([x for x in oku() if x["ad"] != ad] + [r])
    return r


def degis(ad, **alan):
    items = oku()
    for r in items:
        if r["ad"] == ad:
            r.update(alan)
            _yaz(items)
            return r
    return None


def sil(ad):
    items = oku()
    _yaz([r for r in items if r["ad"] != ad])
    return len(items) != len(oku())


def ozet_satiri(r):
    dur = "" if r.get("durum") == "aktif" else T(" (duraklatıldı)", " (paused)")
    return f"{'⏰ ' if r.get('tur') == 'hatirlat' else ''}{r['ad']} [{r['zaman']}]{dur}: {r['is'][:120]}"


def isler(bas, hatir=None):
    """Active routines as scheduler jobs, keyed 'rutin:<name>' ('rutin:<name>@21:00' for each extra time). bas(name,
    text) builds the prompt; the text's braces are doubled because the scheduler fills the prompt with str.format.
    A reminder routine gets `run` = hatir(text, time) instead: no model; hatir says how late a catch-up is."""
    out = {}
    for r in oku():
        if r.get("durum") != "aktif":
            continue
        hat = r.get("tur") == "hatirlat" and hatir
        # missed asleep: run on wake. A daily reminder (pills) only within 2 hours: the next dose is near and a 10-hour
        # late one could double it. A weekly/monthly one (bill day, swimming) would otherwise vanish for days.
        seyrek = "weekday" in r or "monthday" in r
        job = {k: r[k] for k in ("every", "between") if k in r} | {"late": 2 if hat and not seyrek else 24}
        if "weekday" in r:
            job["weekday"] = tuple(r["weekday"])
        if "monthday" in r:
            job["monthday"] = tuple(r["monthday"])
        if "month" in r:
            job["month"] = tuple(r["month"])
        for i, at in enumerate(r.get("ats") or [r.get("at")]):
            j = {**job, **({"at": at} if at else {})}
            if hat:
                j["run"] = lambda m=r["is"], a=at: hatir(m, a)
            else:
                j["prompt"] = bas(r["ad"], r["is"].replace("{", "{{").replace("}", "}}"))
            out["rutin:" + r["ad"] + (f"@{at}" if i else "")] = j
    return out


def cli(args):
    """rutin ekle <name> <when> "<what to do>"   when: 08:30 | 09:00,21:00 | mon,fri@08:30 | 1,15@09:00 | 20@09:00 jan,jul | 90m | 90m@07:00-01:00
    rutin hatirlat <name> <when> "<text>"   (sends the text itself at that time, no AI: pills, a call)
    rutin liste | dur <name> | devam <name> | sil <name>
    Returns (text, ok); a script calling it gets exit code 1 when ok is False."""
    alt = {"add": "ekle", "list": "liste", "pause": "dur", "resume": "devam", "remove": "sil", "remind": "hatirlat"}.get(
        args[0], args[0]) if args else "liste"
    try:
        if alt in ("ekle", "hatirlat") and len(args) == 4:
            return ozet_satiri(ekle(*args[1:], hatirlat=alt == "hatirlat")), True
        if alt == "liste":
            return "\n".join(map(ozet_satiri, oku())) or T("rutin yok", "no routines"), True
        if alt in ("dur", "devam") and len(args) == 2:
            r = degis(adla(args[1]), durum="duraklat" if alt == "dur" else "aktif")
            return (ozet_satiri(r), True) if r else (T("bulunamadı", "not found"), False)
        if alt == "sil" and len(args) == 2:
            return (T("silindi", "removed"), True) if sil(adla(args[1])) else (T("bulunamadı", "not found"), False)
    except ValueError as e:
        return str(e), False
    return T('Kullanım: rutin ekle <ad> <zaman> "<yapılacak iş>"  (zaman: 08:30 | pzt,cum@08:30 | 90dk) | hatirlat | liste | dur | devam | sil <ad>',
             cli.__doc__), False
