"""Calendar events from a private iCal link: works with any agent CLI, no calendar tool or OAuth needed.

Google Calendar: Settings > your calendar > "Secret address in iCal format". Outlook: Settings > Calendar > Shared
calendars > Publish. iCloud: share the calendar as public. Put the link in secrets/keys.env as PENTARCH_ICAL=<url>
(several calendars: separate the links with spaces). The link is a password; it never reaches the agent.
    python -I takvim.py          # today
    python -I takvim.py 1        # tomorrow
    python -I takvim.py 0 7      # the next 7 days
"""
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import T  # noqa: E402  (importing config also loads secrets/keys.env)

GUN = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def when(value, params):
    """DTSTART/EXDATE value -> (local naive datetime, all-day?). A Z time is UTC; a TZID one is taken as local."""
    v = value.strip()
    if "VALUE=DATE" in params or len(v) == 8:
        return datetime.strptime(v[:8], "%Y%m%d"), True
    d = datetime.strptime(v[:15], "%Y%m%dT%H%M%S")
    if v.endswith("Z"):
        d = d.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
    return d, False


def events(text):
    """VEVENTs as dicts: start, allday, summary, rrule (dict), exdates (set of datetimes)."""
    lines = []
    for raw in text.replace("\r\n", "\n").split("\n"):  # unfold: a line starting with a space continues the last one
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    out, ev = [], None
    for line in lines:
        if line == "BEGIN:VEVENT":
            ev = {"exdates": set(), "summary": "", "rrule": {}}
        elif line == "END:VEVENT" and ev is not None:
            if "start" in ev or "recurid" in ev:
                out.append(ev)
            ev = None
        elif ev is not None and ":" in line:
            head, _, value = line.partition(":")
            name, _, params = head.partition(";")
            try:
                if name == "DTSTART":
                    ev["start"], ev["allday"] = when(value, params)
                elif name == "SUMMARY":
                    ev["summary"] = value.replace("\\,", ",").replace("\\;", ";").replace("\\n", " ")
                elif name == "RRULE":
                    ev["rrule"] = dict(p.partition("=")[::2] for p in value.split(";"))
                elif name == "EXDATE":
                    ev["exdates"] |= {when(x, params)[0] for x in value.split(",")}
                elif name == "STATUS":
                    ev["status"] = value
                elif name == "UID":
                    ev["uid"] = value
                elif name == "RECURRENCE-ID":  # one occurrence of a series, moved or cancelled
                    ev["recurid"] = when(value, params)[0]
            except ValueError:
                pass
    # An override replaces its slot in the series: the slot becomes an exdate, the override shows on its own
    # (as a plain one-off) unless it was cancelled.
    tasindi = {(e.get("uid"), e["recurid"]) for e in out if "recurid" in e}
    for e in out:
        if "recurid" not in e and e.get("rrule"):
            e["exdates"] |= {r for u, r in tasindi if u == e.get("uid")}
    return [dict(e, rrule={}) if "recurid" in e else e for e in out
            if "start" in e and e.get("status") != "CANCELLED"]


def ayin_gunleri(yil, ay, byday, saat):
    """Days of one month matching a MONTHLY BYDAY list, at the series' time of day."""
    bas = datetime(yil, ay, 1, saat.hour, saat.minute, saat.second)
    gunler = [bas + timedelta(days=k) for k in range(31) if (bas + timedelta(days=k)).month == ay]
    out = []
    for p in byday.split(","):
        p = p.strip()
        if p[-2:] not in GUN:
            continue
        uyan = [d for d in gunler if d.weekday() == GUN[p[-2:]]]
        try:
            out += [uyan[int(p[:-2]) - 1 if int(p[:-2]) > 0 else int(p[:-2])]] if p[:-2] else uyan
        except (ValueError, IndexError):  # no 5th Tuesday this month
            pass
    return out


def occurrences(ev, start, end):
    """Start times of ev inside [start, end). Covers FREQ DAILY/WEEKLY(+BYDAY)/MONTHLY(+BYDAY)/YEARLY, INTERVAL,
    COUNT, UNTIL."""
    s, r = ev["start"], ev["rrule"]
    if not r:
        return [s] if start <= s < end else []
    freq, step = r.get("FREQ"), int(r.get("INTERVAL") or 1)
    count = int(r["COUNT"]) if r.get("COUNT") else None
    until = when(r["UNTIL"], "")[0] if r.get("UNTIL") else None
    days = [GUN[d[-2:]] for d in r.get("BYDAY", "").split(",") if d[-2:] in GUN] if freq == "WEEKLY" else []
    out, n, i = [], 0, 0
    while i < 5000:  # enough for 13 years of a daily event; the window is days, so this ends long before
        if freq == "DAILY":
            batch = [s + timedelta(days=i * step)]
        elif freq == "WEEKLY":
            week = s - timedelta(days=s.weekday()) + timedelta(weeks=i * step)
            batch = sorted(week + timedelta(days=d) for d in (days or [s.weekday()]))
            batch = [b for b in batch if b >= s]
        elif freq == "MONTHLY" and r.get("BYDAY"):  # 2TU = second Tuesday, -1FR = last Friday, MO = every Monday
            m = s.month - 1 + i * step
            batch = sorted(b for b in ayin_gunleri(s.year + m // 12, m % 12 + 1, r["BYDAY"], s) if b >= s)
        elif freq in ("MONTHLY", "YEARLY"):
            m = s.month - 1 + (i * step if freq == "MONTHLY" else i * step * 12)
            try:
                batch = [s.replace(year=s.year + m // 12, month=m % 12 + 1)]
            except ValueError:  # the 31st in a short month is skipped, as the RFC says
                batch = []
        else:
            return []
        for b in batch:
            if (until and b > until) or b >= end:
                return out
            n += 1
            if count and n > count:
                return out
            if b >= start and b not in ev["exdates"]:
                out.append(b)
        i += 1
    return out


def fetch(url):
    if url.startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    req = urllib.request.Request(url, headers={"User-Agent": "pentarch-calendar"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def main():
    if sys.argv[1:2] in (["-h"], ["--help"]):
        sys.exit(__doc__)
    urls = os.environ.get("PENTARCH_ICAL", "").split()
    if not urls:
        sys.exit(T("Takvim bağlı değil: secrets/keys.env içine PENTARCH_ICAL=<gizli iCal adresi> ekle (python -I takvim.py -h).",
                   "No calendar linked: add PENTARCH_ICAL=<secret iCal address> to secrets/keys.env (python -I takvim.py -h)."))
    offset = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    span = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    start = datetime.combine(date.today() + timedelta(days=offset), datetime.min.time())
    end = start + timedelta(days=span)
    rows, failed = [], 0
    for url in urls:
        try:
            for ev in events(fetch(url)):
                rows += [(o, ev) for o in occurrences(ev, start, end)]
        except Exception as e:
            failed += 1
            print(T(f"takvim okunamadı ({type(e).__name__})", f"calendar unreadable ({type(e).__name__})"))
    if not rows and not failed:
        print(T(f"{start:%d.%m}: takvimde etkinlik yok.", f"{start:%d.%m}: nothing on the calendar."))
    for o, ev in sorted(rows, key=lambda x: (x[0], x[1]["summary"])):
        saat = T("tüm gün", "all day") if ev["allday"] else f"{o:%H:%M}"
        print(f"{o:%d.%m} {saat} {ev['summary'][:120]}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
