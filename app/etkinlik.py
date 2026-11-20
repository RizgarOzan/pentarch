"""Add an event to any calendar with no OAuth: builds an .ics file and sends it to the owner's Telegram.

Tapping the file on the phone offers Google, Apple or Outlook calendar. Nothing is written to a calendar here.
  python -I pentarch.py etkinlik 2026-12-05 14:30 "Dentist" [minutes]     # minutes default 60
  python -I pentarch.py etkinlik 2026-12-05 "Mum's birthday"              # no time = all-day
"""
import datetime as dt
import re
import uuid

from config import HOME, T

TARIH = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SAAT = re.compile(r"^\d{1,2}:\d{2}$")


def _esc(s):
    s = "".join(" " if (ord(c) < 32 and c != "\t") or c in "\x7f\x85\u2028\u2029" else c for c in s)  # line-break lookalikes some parsers split on
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")


def olustur(gun, saat, baslik, dk=60, simdi=None):
    """iCalendar text (CRLF). `saat` None = all-day. Floating local time, so it lands at the same wall-clock time."""
    simdi = simdi or dt.datetime.now(dt.timezone.utc)
    d = dt.date.fromisoformat(gun)
    satirlar = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//pentarch//etkinlik//EN", "CALSCALE:GREGORIAN", "BEGIN:VEVENT",
                f"UID:{uuid.uuid4()}@pentarch", f"DTSTAMP:{simdi:%Y%m%dT%H%M%SZ}", f"SUMMARY:{_esc(baslik.strip())}"]
    if saat:
        h, m = (int(x) for x in saat.split(":"))
        bas = dt.datetime.combine(d, dt.time(h, m))
        satirlar += [f"DTSTART:{bas:%Y%m%dT%H%M%S}", f"DTEND:{bas + dt.timedelta(minutes=dk):%Y%m%dT%H%M%S}"]
    else:
        satirlar += [f"DTSTART;VALUE=DATE:{d:%Y%m%d}", f"DTEND;VALUE=DATE:{d + dt.timedelta(days=1):%Y%m%d}"]
    satirlar += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(satirlar) + "\r\n"


def cli(args):
    """Returns (message, ok). Sends the file to Telegram when an owner is paired."""
    a = list(args)
    kullanim = T('Kullanım: etkinlik 2026-12-05 14:30 "Başlık" [dakika]  (saat yoksa tüm gün)',
                 'Usage: etkinlik 2026-12-05 14:30 "Title" [minutes]  (no time = all-day)')
    if len(a) < 2 or not TARIH.match(a[0]):
        return kullanim, False
    gun, saat = a[0], (a[1] if SAAT.match(a[1]) else None)
    kalan = a[2 if saat else 1:]
    dk = 60
    if saat and len(kalan) > 1 and kalan[-1].isascii() and kalan[-1].isdecimal():
        dk = int(kalan.pop())
    baslik = " ".join(kalan).strip()
    try:
        dt.date.fromisoformat(gun)
        if saat and not (int(saat.split(":")[0]) < 24 and int(saat.split(":")[1]) < 60):
            raise ValueError
    except ValueError:
        return T("Tarih ya da saat geçersiz.", "Invalid date or time."), False
    if not baslik or not 1 <= dk <= 24 * 60:
        return kullanim, False
    klasor = HOME / "tmp"
    klasor.mkdir(parents=True, exist_ok=True)
    yol = klasor / "etkinlik.ics"
    yol.write_text(olustur(gun, saat, baslik, dk), encoding="utf-8", newline="")
    nerede = f"{gun} {saat}" if saat else gun
    try:
        import tg
        state = tg.load_state()
        if state.get("chat_id") is None:
            raise RuntimeError("no owner")
        tg.send_doc(state, yol, T(f"Takvime ekle: {baslik} ({nerede})", f"Add to calendar: {baslik} ({nerede})"))
    except BaseException as e:  # send_doc exits on failure
        why = T("henüz Telegram'a bağlı değilsin (setup'ı bitir)", "Telegram is not paired yet (finish setup)") if "no owner" in str(e) else repr(e)
        return T(f"Takvim dosyası hazır ama Telegram'a gitmedi: {why}. Dosya: {yol}", f"The calendar file is ready but did not reach Telegram: {why}. File: {yol}"), False
    return T(f"Etkinlik dosyası Telegram'a gitti: {baslik} ({nerede}). Dokununca takvime eklenir.",
             f"Event file sent to Telegram: {baslik} ({nerede}). Tap it to add to your calendar."), True
