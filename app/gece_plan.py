"""What will run while the owner sleeps: pause state, quiet hours, the scheduled jobs (from JOBS in pentarch.py) that
fall between now and the end of quiet hours, tasks and reminders that come due, and news held for the morning.
Answers "will it really work tonight?" after a "do it all overnight" or a "stop everything".

Usage: python -I gece_plan.py
"""
import json
import sys
from datetime import datetime, timedelta

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))  # python -I leaves the script's folder off the path
from config import T


def _load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _icinde(hm, between):
    start, end = between
    return start <= hm or hm < end if end < start else start <= hm < end


def gece_isleri(jobs, off, t, son):
    """[(name, when)] of jobs that run between t and son. Daily jobs give their time; interval jobs how many runs."""
    out = []
    for name, job in jobs.items():
        if name in off:
            continue
        if "at" in job:
            h, m = map(int, job["at"].split(":"))
            for gun in (0, 1):
                occ = (t + timedelta(days=gun)).replace(hour=h, minute=m, second=0, microsecond=0)
                wd = job.get("weekday")
                if wd is not None and occ.weekday() not in (wd if isinstance(wd, tuple) else (wd,)):
                    continue
                if t <= occ <= son:
                    out.append((name, f"{occ:%H:%M}"))
        elif "every" in job:
            dk = sum(_icinde((t + timedelta(minutes=i)).strftime("%H:%M"), job["between"])
                     for i in range(0, int((son - t).total_seconds() // 60), 10)) * 10
            if dk >= job["every"]:
                out.append((name, T(f"{job['every']} dk'da bir, ~{dk // job['every']} kez",
                                    f"every {job['every']} min, ~{dk // job['every']} times")))
    return sorted(out, key=lambda x: x[1])


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    import pentarch as p
    t = datetime.now()
    bas, bit = p.ayar("sessiz")
    h, m = map(int, bit.split(":"))
    son = t.replace(hour=h, minute=m, second=0, microsecond=0)
    if son <= t:
        son += timedelta(days=1)
    dur = p.paused()
    print(T(f"DURAKLATILMIŞ, bitiş {dur}: görevler ve zamanlı işler çalışmaz", f"PAUSED until {dur}: tasks and jobs do not run")
          if dur else T("Duraklatma yok: işler vadesinde çalışır", "Not paused: jobs run when due"))
    print(T(f"Sessiz saat {bas}-{bit}: otomatik haberler sabaha birikir", f"Quiet hours {bas}-{bit}: automatic news waits for the morning"))
    isler = gece_isleri(p.all_jobs(),set(p.ayar("kapali_isler")), t, son)
    print(T(f"{son:%d.%m %H:%M}'e kadar zamanlı iş: {len(isler)}", f"Scheduled jobs until {son:%d.%m %H:%M}: {len(isler)}"))
    for name, when in isler:
        print(f"  {when}  {name}")
    sinir = f"{son:%Y-%m-%d %H:%M}"
    gor = sorted((g for g in _load(p.TASKS) if g.get("zaman", "9") <= sinir), key=lambda g: g["zaman"])
    print(T(f"Vadesi gelen görev: {len(gor)}", f"Tasks coming due: {len(gor)}")
          + (T(f" (günlük görev tavanı {p.task_cap():g}$)", f" (daily task cap {p.task_cap():g}$)") if gor else ""))
    for g in gor:
        print(f"  {g['zaman']}  {g.get('is', '')[:90]}".replace("\n", " "))
    hat = [r for r in _load(p.REMINDERS) if r.get("zaman", "9") <= sinir]
    print(T(f"Vadesi gelen hatırlatma: {len(hat)}", f"Reminders coming due: {len(hat)}"))
    gece = _load(p.NIGHT_QUEUE)
    print(T(f"Sabah mesajına birikmiş: {len(gece) if isinstance(gece, list) else 0}",
            f"Held for the morning message: {len(gece) if isinstance(gece, list) else 0}"))


if __name__ == "__main__":
    main()
