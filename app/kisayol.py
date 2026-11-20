"""Shortcuts: one short word that runs a few read-only readers and answers with their output. No model, no cost, instant.

    shortcut add <name> = receivables + shifts      kısayol ekle <ad> = alacak + vardiya
    shortcut list | remove <name>                   kısayol liste | sil <ad>
Then sending just `<name>` (or `/<name>`) in the chat answers at once. Readers: alacak (receivables), vardiya (shifts),
ders (study), rutin (routines), tahsilat (nudges: drafted payment reminders to copy, nothing is sent). They only read the owner's own files; nothing is changed or sent anywhere.
Data: <home>/kisayollar.json.
"""
import json
import re

from config import HOME, T
from rutin import AD, adla

DOSYA = HOME / "kisayollar.json"
OKUYUCU = {"alacak": "alacak", "receivables": "alacak", "vardiya": "vardiya", "shifts": "vardiya",
           "ders": "ders", "study": "ders", "tahsilat": "tahsilat", "nudges": "tahsilat", "rutin": "rutin", "routines": "rutin", "routine": "rutin"}
# words that already mean something in the chat: a shortcut with one of these names would hide the real command
AYRIK = {"yardim", "help", "start", "iptal", "kes", "dur", "stop", "cancel", "evet", "hayir", "yes", "no", "ok", "test",
         "durum", "status", "ekle", "add", "sor", "ask", "kisayol", "shortcut", "tartisma", "debate", "konsey", "council",
         *OKUYUCU}
EKLE = re.compile(r"\s*/?(?:kısayol|kisayol|shortcut)\s+(?:ekle|add)\s+(.+?)\s*=\s*(.+)", re.I | re.S)
DIGER = re.compile(r"\s*/?(?:kısayol|kisayol|shortcut)(?:\s+(liste|list|sil|remove)(?:\s+(.+))?)?\s*", re.I)


def oku():
    try:
        return json.loads(DOSYA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _yaz(items):
    DOSYA.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def ekle(ad, adimlar):
    """Save a shortcut; ValueError says why not. adimlar: reader names ('alacak', 'shifts'...)."""
    ad = adla(ad)
    if not AD.match(ad) or len(ad) < 3:
        raise ValueError(T("ad: küçük harf, rakam, tire; en az 3 harf", "name: lowercase letters, digits, dashes; 3 characters at least"))
    if ad in AYRIK:
        raise ValueError(T(f"'{ad}' zaten bir komut, başka bir ad seç", f"'{ad}' is already a command, pick another name"))
    try:
        adimlar = [OKUYUCU[a.strip().lower()] for a in adimlar]
    except KeyError as e:
        raise ValueError(T(f"bilinmeyen okuyucu: {e.args[0]} (alacak, vardiya, ders, rutin)",
                           f"unknown reader: {e.args[0]} (receivables, shifts, study, routines)")) from None
    if not adimlar or len(adimlar) > 4:
        raise ValueError(T("1-4 okuyucu ver, + ile ayır", "give 1-4 readers separated by +"))
    r = {"ad": ad, "adimlar": list(dict.fromkeys(adimlar))}
    _yaz([x for x in oku() if x["ad"] != ad] + [r])
    return r


def sil(ad):
    items = oku()
    _yaz([r for r in items if r["ad"] != adla(ad)])
    return len(items) != len(oku())


def ozet_satiri(r):
    return f"{r['ad']}: " + " + ".join(r["adimlar"])


def _calistir(adim):
    if adim == "alacak":
        import alacak
        return alacak.cli()
    if adim == "tahsilat":
        import alacak
        import datetime
        f = alacak.dosya()
        return alacak.taslaklar(alacak.oku(f), datetime.date.today()) if f else alacak.cli()
    if adim == "vardiya":
        import vardiya
        return vardiya.cli([])
    if adim == "ders":
        import ders
        return ders.cli()
    import rutin
    return rutin.cli([])[0]


def calistir(r):
    parcalar = []
    for adim in r["adimlar"]:
        try:
            cikti = str(_calistir(adim)).strip()
        except Exception as e:  # a broken tracker file must not take the other readers down
            cikti = T(f"okunamadı: {e}", f"could not read: {e}")
        parcalar.append(cikti if len(r["adimlar"]) == 1 else f"— {adim} —\n{cikti}")
    return "\n\n".join(parcalar)


def komut(text):
    """The chat commands that need no model. Returns the reply, or None when the message isn't one."""
    if m := EKLE.fullmatch(text):
        try:
            return "⚡ " + ozet_satiri(ekle(m.group(1), re.split(r"\s*\+\s*|\s*,\s*", m.group(2).strip())))
        except ValueError as e:
            return T(f"Kısayol kaydedilmedi: {e}", f"Shortcut not saved: {e}")
    if m := DIGER.fullmatch(text):
        if (m.group(1) or "").lower() in ("sil", "remove") and m.group(2):
            return T("Silindi.", "Removed.") if sil(m.group(2)) else T("Bulunamadı.", "Not found.")
        return "\n".join("⚡ " + ozet_satiri(r) for r in oku()) or T(
            "Kısayol yok. Örnek: kısayol ekle sabah = alacak + vardiya", "No shortcuts. Example: shortcut add morning = receivables + shifts")
    if len(text) <= 40 and (r := next((x for x in oku() if x["ad"] == adla(text.strip().lstrip("/"))), None)):
        return calistir(r)
    return None
