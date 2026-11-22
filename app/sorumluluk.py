"""Responsibilities: ongoing jobs the assistant owns end to end.

A task is one piece of work. A responsibility is a standing goal ("keep the job tracker current", "watch this repo's
CI") that the assistant keeps on its own: it wakes on a timer or when an event command's output changes, reads its
own notes file, does the next step, writes down what it learned and picks its next wake-up. It sends nothing while
it works. A message goes out only when the goal is done, when a decision is really the owner's, or for real news.

Reply protocol (one per line, anywhere in the reply; everything else is kept as the run's summary, never sent):
  NOT: <line>                 appended to the responsibility's notes file
  SONRAKI: <minutes>          next wake-up (30..1440); otherwise every `her` minutes
  KARAR: <question> || <job>  asks the owner with Yes/No buttons; yes queues <job> as a task
  HABER: <line>               urgent news, sent at once
  BITTI: <result>             goal reached: the responsibility closes and <result> is sent

Data: <home>/sorumluluklar.json, notes in <home>/sorumluluklar/<name>.md. No model call happens here.
"""
import hashlib
import json
import os
import re
import shlex
import subprocess
from datetime import datetime, timedelta

from config import HOME

DOSYA = HOME / "sorumluluklar.json"
NOTLAR = HOME / "sorumluluklar"
FMT = "%Y-%m-%d %H:%M"
AD = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
ALANLAR = ("hedef", "her", "yetki", "izin", "onay", "yasak", "olay")


# The event command runs unattended and without a shell, so it is limited to read-only lookups. A responsibility can be
# created by the agent itself; anything wider would let a prompt injection plant a permanent command.
OLAY_OK = {"gh": {"pr", "issue", "run", "release"}, "git": {"status", "log", "diff", "ls-remote"}}
OLAY_READ = {"view", "list", "checks", "status"}
# Flags are an allowlist, not a denylist: git accepts unique abbreviations (--upl= for --upload-pack), so a blocked
# name can always be spelled another way. Anything starting with "-" that isn't here is refused.
OLAY_FLAGS = {"--porcelain", "--short", "-s", "-b", "--branch", "--oneline", "--stat", "--name-only", "--name-status",
              "--heads", "--tags", "--state", "--limit", "-L", "--json", "--repo", "-R", "--label", "--author",
              "--assignee", "--base", "--head", "--status", "--workflow", "--branch", "--event"}


def olay_argv(cmd):
    """The command as an argv list, or ValueError when it isn't a plain read-only gh/git lookup."""
    try:
        a = shlex.split(cmd)
    except ValueError as e:
        raise ValueError(f"olay: {e}")
    git_dir = a[:1] == ["git"] and a[1:2] == ["-C"] and len(a) > 3
    if git_dir:
        sub, rest = a[3], a[4:]
    else:
        sub, rest = (a[1] if len(a) > 1 else ""), a[2:]
    ok = OLAY_OK.get(a[0] if a else "")
    if not ok or sub not in ok or (a[0] == "gh" and (not rest or rest[0] not in OLAY_READ)):
        raise ValueError("olay: only read-only `gh pr|issue|run|release view|list|checks|status` and "
                         "`git [-C dir] status|log|diff|ls-remote` are allowed (no shell, no pipes)")
    for x in rest:
        if x.startswith("-") and x.partition("=")[0] not in OLAY_FLAGS and not re.fullmatch(r"-\d+", x):
            raise ValueError(f"olay: flag {x.split('=')[0]} is not on the read-only list")
    if a[0] == "git" and sub == "diff":  # a repo's own config can name a program to run for diffs
        i = a.index("diff") + 1
        a[i:i] = ["--no-ext-diff", "--no-textconv"]
    return a


def oku():
    return json.loads(DOSYA.read_text(encoding="utf-8")) if DOSYA.exists() else []


def yaz(items):
    DOSYA.parent.mkdir(parents=True, exist_ok=True)
    DOSYA.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def bul(ad):
    return next((s for s in oku() if s["ad"] == ad), None)


def ekle(ad, hedef, her=240, yetki="oku", izin="", onay="", yasak="", olay="", t=None):
    """New responsibility. yetki: "oku" (read-only run) or "yaz" (may edit files). olay: a read-only gh/git command (see olay_argv); when its
    output changes the responsibility wakes (checked every `her` minutes, no model call while it stays the same)."""
    if not AD.match(ad):
        raise ValueError("name: lowercase letters, digits and '-', at most 40")
    if bul(ad):
        raise ValueError(f"{ad} already exists")
    if yetki not in ("oku", "yaz"):
        raise ValueError("yetki: oku | yaz")
    if olay:
        olay_argv(olay)
    her = int(her)
    if not 30 <= her <= 1440:
        raise ValueError("her: 30..1440 minutes")
    s = {"ad": ad, "hedef": hedef.strip(), "her": her, "yetki": yetki, "izin": izin, "onay": onay, "yasak": yasak,
         "olay": olay, "durum": "aktif", "kayit": (t or datetime.now()).strftime(FMT), "son": "", "sonraki": "",
         "ozet": ""}
    yaz(oku() + [s])
    return s


def degis(ad, **alan):
    items = oku()
    for s in items:
        if s["ad"] == ad:
            s.update(alan)
            yaz(items)
            return s
    return None


def sil(ad):
    items = oku()
    yaz([s for s in items if s["ad"] != ad])
    return len(items) != len(oku())


def not_dosyasi(ad):
    return NOTLAR / f"{ad}.md"


def notlar(ad, n=60):
    p = not_dosyasi(ad)
    return p.read_text(encoding="utf-8").splitlines()[-n:] if p.exists() else []


def not_ekle(ad, satirlar, t):
    if not satirlar:
        return
    NOTLAR.mkdir(parents=True, exist_ok=True)
    with not_dosyasi(ad).open("a", encoding="utf-8") as f:
        f.writelines(f"- {t} {' / '.join(x.splitlines())}\n" for x in satirlar)  # one note, one line


def vakti(s, t):
    """Is it time to wake? Paused or finished ones never are. SONRAKI wins over the `her` interval."""
    if s["durum"] != "aktif":
        return False
    if s.get("sonraki"):
        return t >= datetime.strptime(s["sonraki"], FMT)
    return not s.get("son") or t - datetime.strptime(s["son"], FMT) >= timedelta(minutes=s["her"])


def olay_degisti(s):
    """Runs the event command; True when its output differs from last time. The first reading only records."""
    try:
        # -C may point at any repo, and git would run that repo's fsmonitor hook; switch it off
        env = {**os.environ, "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.fsmonitor", "GIT_CONFIG_VALUE_0": "false"}
        p = subprocess.run(olay_argv(s["olay"]), capture_output=True, encoding="utf-8", errors="replace", timeout=60, env=env)
        cikti = p.stdout + p.stderr
    except Exception as e:
        cikti = f"error: {e!r}"
    iz = hashlib.sha1(cikti.encode()).hexdigest()[:16]
    eski = s.get("iz")
    degis(s["ad"], iz=iz)
    return eski is not None and iz != eski


def istem(s, owner, lang, t):
    kurallar = "\n".join(f"- {k}: {s[a]}" for a, k in (("izin", "Allowed without asking"),
                                                        ("onay", "Ask first (KARAR)"), ("yasak", "Never")) if s.get(a))
    yetki = ("You may edit files." if s["yetki"] == "yaz" else
             "This run is read-only: anything that changes a file or the outside world goes through KARAR.")
    gecmis = "\n".join(notlar(s["ad"])) or "(no notes yet: this is the first run)"
    return f"""[Responsibility "{s['ad']}", {t:%Y-%m-%d %H:%M}] This is an automatic run; read only what the job needs.
You own this goal for {owner} until it is done:
{s['hedef']}

{yetki}
{kurallar}
Anything that leaves this machine (a message, an e-mail, a push, a post, a delete) always goes through KARAR first.

Your notes so far (newest last):
{gecmis}

Do the next useful step now. {owner} does not want progress reports: nothing you write is sent except these lines
(one per line, in {lang}):
NOT: <what you did or learned; the next run reads it>   (write at least one)
SONRAKI: <minutes>   (when to look again, 30..1440; skip it to wait {s['her']} min)
KARAR: <one-sentence question to {owner}> || <the full job to do if they say yes>
HABER: <only for news {owner} would want right now>
BITTI: <the result, when the goal is reached>
If there is nothing to do yet, write one NOT line and stop."""


def ayristir(cevap):
    """Splits a reply into protocol lines. Unknown text becomes the summary, which is never sent."""
    out = {"not": [], "sonraki": None, "karar": [], "haber": [], "bitti": None, "ozet": []}
    for satir in (cevap or "").splitlines():
        x = satir.strip().lstrip("*-• ").replace("**", "")
        anahtar, _, deger = x.partition(":")
        deger = deger.strip()
        k = anahtar.strip().upper()
        if k == "NOT" and deger:
            out["not"].append(deger)
        elif k == "SONRAKI" and (m := re.search(r"\d+", deger)):
            out["sonraki"] = min(1440, max(30, int(m.group())))
        elif k == "KARAR" and "||" in deger:
            soru, is_ = (y.strip() for y in deger.split("||", 1))
            if soru and is_:
                out["karar"].append((soru, is_))
        elif k == "HABER" and deger:
            out["haber"].append(deger)
        elif k in ("BITTI", "BİTTİ") and deger:
            out["bitti"] = deger
        elif x:
            out["ozet"].append(x)
    return out


def isle(ad, cevap, t):
    """Writes the run's result back: notes, next wake-up, state. Returns what has to be sent (karar, haber, bitti)."""
    r = ayristir(cevap)
    hata = (cevap or "").startswith(("Hata:", "Error:"))
    if hata:
        r["not"].append(f"run failed: {cevap[:200]}")
    elif not r["not"] and r["ozet"]:
        r["not"].append(" ".join(r["ozet"])[:300])  # the model forgot NOT: keep its summary so the next run knows
    not_ekle(ad, r["not"], t.strftime(FMT))
    dk = r["sonraki"] if r["sonraki"] and not hata else None
    degis(ad, son=t.strftime(FMT), sonraki=(t + timedelta(minutes=dk)).strftime(FMT) if dk else "",
          ozet=" ".join(r["ozet"])[:300], **({"durum": "bitti", "sonuc": r["bitti"]} if r["bitti"] else {}))
    return r


def ozet_satiri(s):
    ne = {"aktif": "active", "duraklat": "paused", "bitti": "done"}.get(s["durum"], "?")
    zaman = s.get("sonraki") or s.get("son") or s.get("kayit", "")
    return f"{ne} {s['ad']} ({s['yetki']}, {s['her']} min, {zaman}): {s['hedef'][:80]}"
