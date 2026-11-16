"""Tiered routing for ledger jobs: cheap -> mid -> top, with a manager review in between.

A job starts on the cheapest tier that can be trusted with it (kademe_sec):
- top (deep_model) straight away only when the owner's own message asks for the strong model, or the job is an
  architecture change or a multi-file code change;
- mid (fast_model, full agent run with tools) when the job needs tools or touches personal data;
- cheap (the OpenAI-compatible providers, no tools) only when a machine can check the answer: Python with the
  caller's asserts, a JSON schema, or values that must appear in a given source. Anything else starts at mid.
Each cheap provider gets KADEME_HAK failed checks, then the next one; if none passes the job goes to mid.
A cheap or mid result is reviewed by the deep model against the owner's request; a MISSING verdict reruns the job on
the top tier with the failed attempt attached. If the reviewer itself fails, the result counts as fine (the job is
not lost). Every job is one line in <home>/sirket/kademe.jsonl; ozet() summarises it.

Config (pentarch.json, read with a default, nothing added to config.py):
  "routing": {"enabled": false}   off = kos() runs the job once on the runner's default model, as before.

Wiring in pentarch.py:
  import sirket
  # agir_kos: replace `reply = run_claude(<prompt>, resume=False)` with
  reply = sirket.kos(<prompt>, i["tarif"], i["istek"], lambda p, m: run_claude(p, model=m, resume=False),
                     no=no, durdu=lambda: no in is_iptal)
  # CLI command table: `pentarch.py routing [days]`
  if cmd == "routing": print(sirket.ozet(int(sys.argv[2]) if len(sys.argv) > 2 else 7))
"""
import ast
import json
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import C, HOME, T  # noqa: E402
import agents  # noqa: E402
import magi  # noqa: E402

FAST, DEEP = C["agent"]["fast_model"], C["agent"]["deep_model"]
KAYIT = HOME / "sirket" / "kademe.jsonl"
KADEME_HAK = 2  # failed checks one cheap provider gets before the next one

# Personal data never goes to the cheap tier (agents.istek also masks e-mails, phones, IBANs for untrusted providers)
KISISEL = re.compile(r"e-?mail|e-?posta|gmail|\bcv\b|résumé|\bresume\b|özgeçmiş|başvur|job application|telegram|"
                     r"password|şifre|parola|passport|pasaport|kimlik|\bid number|iban|card number|kart no", re.I)
# Needs tools (files, repos, web, messaging): the cheap tier has none
ARAC_ISI = re.compile(r"\bfile|dosya|folder|klasör|\brepo|github|\bpr\b|commit|\bpush|browser|chrome|\bmail|discord|"
                      r"whatsapp|linkedin|notion|drive|calendar|takvim|\bweb|site|\bpage|sayfa|internet|search|\barama|"
                      r"araştır|research|çalıştır|\brun\b|command|komut|\bsend|gönder|\bapply|\bform|download|indir|"
                      r"upload|yükle|\bpdf|slide|slayt|screen|ekran|\blogs?\b|\.py\b|\.md\b|https?://", re.I)
GUCLU = re.compile(rf"\b{re.escape(DEEP)}\b|\bderin(?:lemesine|den)?\b|\bin depth\b|\bdeep model\b|"
                   r"\bstrong(?:est)? model\b|en güçlü model|güçlü model", re.I)
# The word "architecture" alone is not enough: in past jobs it was mostly a side remark ("you decide the architecture")
MIMARI = re.compile(r"mimari(?:yi|sini)? (?:olarak )?(?:değiştir|yeniden|tasarla|kur)|mimari (?:değişikli|dönüşü|tasarı)|"
                    r"yeniden (?:tasarla|yapılandır)|refakt[öo]r|refactor|redesign|restructure|"
                    r"(?:change|rework|new) (?:the )?architecture|architecture (?:change|rework)", re.I)
COK_DOSYA = re.compile(r"(?:çok|birden (?:çok|fazla)|birkaç|several|multiple|many|\b[3-9]) (?:dosya|files)", re.I)
KOD = re.compile(r"\bkod|\bcode|\.py\b|\.cs\b|\.ts\b|\.js\b|fonksiyon|function|modül|module|betik|script", re.I)
YASAK_KOD = re.compile(r"\b(os|subprocess|socket|shutil|requests|urllib|ctypes|sys)\b\s*(\.|import)|__import__|\beval\(|"
                       r"\bexec\(|\bopen\(|\bimport\s+(os|subprocess|socket|shutil|sys)\b")
TIPLER = {"str": str, "int": int, "float": (int, float), "bool": bool, "list": list, "dict": dict, "null": type(None)}

KOD_ISTEM = ("Python 3, standard library only. Write one ```python block and nothing outside it. The code must contain "
             "asserts that test it. No file, network or process access.")
JSON_ISTEM = "Answer with JSON only, nothing else. Do not invent values: use only what the input contains."
DENETCI = T("Bir ekibin müdürüsün. Bir çalışan sahibin isteği üzerine işi yaptı. Sonucu isteğin kendisiyle karşılaştır: istenen "
            "her şey yapılmış ve cevapta söylenmiş mi, uydurma ya da çelişki var mı, yarım kalmış mı. Sonuç yalnız iddia "
            "ediyorsa (\"ekledim\") ve iddia isteği karşılıyorsa yeterli say. İlk satıra yalnız UYGUN ya da EKSIK yaz; EKSIK "
            "ise aynı satırda iki noktadan sonra tek cümle neden.",
            "You are a team's manager. A worker did a job on the owner's request. Compare the result with the request "
            "itself: is everything asked done and stated in the answer, is anything invented or contradictory, is it "
            "half-finished. If the result only claims (\"I added it\") and the claim meets the request, count it as "
            "enough. Write only OK or MISSING on the first line; for MISSING add a colon and one sentence why.")


def testleri_ayikla(metin):
    """`assert ...` statements in the job text (one per line or several on one line)."""
    return "\n".join(x.strip().rstrip(";") for x in re.findall(r"\bassert\s.+?(?=\s*;?\s*\bassert\s|\n|$)", metin))


def kod_ayikla(c):
    m = re.search(r"```(?:python)?\s*\n(.*?)```", c, re.S)
    return (m.group(1) if m else c).strip()


def kod_sina(c, testler=""):
    """Parses, refuses file/network/process calls, runs with the caller's asserts appended (10 s, isolated temp dir)."""
    kod = kod_ayikla(c)
    try:
        ast.parse(kod)
    except SyntaxError as e:
        return False, f"syntax: {e}"
    if YASAK_KOD.search(kod):
        return False, "forbidden call (file/network/process)"
    if "assert" not in kod + testler:
        return False, "no assert"
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "t.py"
        p.write_text(kod + ("\n\n" + testler if testler else ""), encoding="utf-8")
        try:
            r = subprocess.run([sys.executable, "-I", str(p)], cwd=d, capture_output=True, text=True, timeout=10,
                               encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            return False, "over 10 s"
    return r.returncode == 0, (r.stderr or "")[-200:]


def _json_ayikla(c):
    m = re.search(r"[\[{].*[\]}]", c, re.S)
    return json.loads(m.group(0)) if m else json.loads(c)


def sema_sina(c, sema):
    """A JSON object or list of objects; each has exactly the schema's keys with matching types ('str|null' allowed)."""
    try:
        j = _json_ayikla(c)
    except ValueError as e:
        return False, f"bad json: {e}"
    satir = j if isinstance(j, list) else [j]
    if not satir:
        return False, "empty list"
    for x in satir:
        if not isinstance(x, dict):
            return False, "not an object"
        if set(x) != set(sema):
            return False, f"keys {sorted(x)} != {sorted(sema)}"
        for k, t in sema.items():
            ad = t.split("|")
            if isinstance(x[k], bool) and "bool" not in ad or not isinstance(x[k], tuple(TIPLER[a] for a in ad)):
                return False, f"{k}: {type(x[k]).__name__} != {t}"
    return True, f"schema holds ({len(satir)} objects)"


def _yaprak(j):
    if isinstance(j, dict):
        for v in j.values():
            yield from _yaprak(v)
    elif isinstance(j, list):
        for v in j:
            yield from _yaprak(v)
    elif j is not None and not isinstance(j, bool):
        yield j


def kaynak_sina(c, kaynak):
    """Every text/number value in the output must occur in the source (case and spacing ignored): invented values fail."""
    try:
        j = _json_ayikla(c)
    except ValueError as e:
        return False, f"bad json: {e}"
    duz = lambda x: re.sub(r"\s+", " ", str(x)).strip().casefold()  # noqa: E731
    k, deger = duz(kaynak), list(_yaprak(j))
    if not deger:
        return False, "no values"
    for v in deger:
        adaylar = {duz(v)} | ({duz(int(v)), duz(v).replace(".", ",")} if isinstance(v, float) and v == int(v) else
                             {duz(v).replace(".", ",")} if isinstance(v, float) else set())
        if not any(a and a in k for a in adaylar):
            return False, f"not in source: {str(v)[:40]}"
    return True, f"{len(deger)} values in source"


def sinayici(sema=None, kaynak=None, testler=""):
    """The machine check for a job, or None when nothing can check it (then it never goes to the cheap tier)."""
    if sema or kaynak:
        def f(c):
            ok, a = sema_sina(c, sema) if sema else (True, "")
            if ok and kaynak:
                ok, a2 = kaynak_sina(c, kaynak)
                a = f"{a}; {a2}".strip("; ")
            return ok, a
        return f
    if testler:
        return lambda c: kod_sina(c, testler)
    return None


def kademe_sec(tarif, istek="", sinanir=False):
    """(tier, reason): 'top', 'mid' or 'cheap'. Only the owner's own message (istek) can ask for the strong model; a model
    name inside the job text is the brain's hint, not a decision."""
    if m := GUCLU.search(istek):
        return "top", f"owner asked: \"{m.group(0)}\""
    if m := MIMARI.search(tarif):
        return "top", f"architecture: \"{m.group(0)}\""
    if (m := COK_DOSYA.search(tarif)) and KOD.search(tarif):
        return "top", f"multi-file code: \"{m.group(0)}\""
    if m := KISISEL.search(f"{tarif}\n{istek}"):
        return "mid", f"personal data: \"{m.group(0)}\""
    if m := ARAC_ISI.search(re.sub(r"\bassert\s.*", "", tarif)):
        return "mid", f"needs tools: \"{m.group(0)}\""
    if not sinanir:
        return "mid", "no machine check"
    return "cheap", "machine-checkable, no tools"


def ucuz(tarif, sina, kod=False):
    """Cheap tier: each provider in order, KADEME_HAK checked tries each. (answer, model) or (None, None)."""
    sistem = KOD_ISTEM if kod else JSON_ISTEM
    for api in agents.providers():
        metin = tarif
        for _ in range(KADEME_HAK):
            try:
                c, _u = agents.istek(api, [{"role": "system", "content": sistem}, {"role": "user", "content": metin}],
                                     timeout=120)
            except Exception:
                break  # provider down or refused: next provider
            ok, neden = sina(c)
            if ok:
                return c, api["model"]
            metin = f"{tarif}\n\nYour previous answer failed the check: {neden}\nPrevious answer:\n{c[:2000]}"
    return None, None


def denetle(istek, tarif, sonuc):
    """Manager review by the deep model: (fine, reason). A reviewer that fails counts as fine."""
    try:
        c = magi.agent_sor(DEEP, DENETCI, T(f"Sahibin isteği:\n{istek}\n\nİş tarifi:\n{tarif}\n\nÇalışanın sonucu:\n",
                                            f"Owner's request:\n{istek}\n\nThe job:\n{tarif}\n\nWorker's result:\n")
                           + sonuc[:6000], timeout=180)
    except Exception as e:
        return True, f"reviewer failed: {e!r}"[:120]
    ilk = (c or "").strip().splitlines()[0] if (c or "").strip() else ""
    return not ilk.upper().lstrip("*# ").startswith(("EKSIK", "MISSING")), ilk.partition(":")[2].strip() or ilk


def kos(prompt, tarif, istek, run, no=None, sema=None, kaynak=None, testler=None, durdu=lambda: False):
    """Runs one job through the tiers and returns the reply. run(prompt, model) is the agent runner (model None = its
    default); sema/kaynak/testler are optional machine checks (asserts are also read from the job text)."""
    if not C.get("routing", {}).get("enabled"):
        return run(prompt, None)
    testler = testler or testleri_ayikla(tarif)
    sina = sinayici(sema, kaynak, testler)
    secim, gerekce = kademe_sec(tarif, istek, sina is not None)
    kademe, adimlar, reply, t0 = secim, [], None, time.monotonic()
    if kademe == "cheap":
        reply, model = ucuz(tarif, sina, kod=not (sema or kaynak))
        adimlar.append({"kademe": "cheap", "model": model, "gecti": reply is not None})
        if reply is None:
            kademe = "mid"
    if kademe == "mid":
        reply = run(prompt, FAST)
        adimlar.append({"kademe": "mid", "model": FAST})
    if reply is not None and not durdu():
        if reply.startswith(("Hata", "Error")):
            uygun, neden = False, reply[:120]
        else:
            uygun, neden = denetle(istek, tarif, reply)
        adimlar.append({"kademe": "review", "model": DEEP, "karar": "OK" if uygun else "MISSING", "neden": neden})
        if not uygun:
            prompt += T(f"\n\n[Daha ucuz bir kademe bu işi denedi; müdür denetimi eksik buldu: {neden}\nOnun sonucu:\n"
                        f"{reply[:3000]}\nYapılmışı tekrarlama; dışa giden bir şeyi (mesaj, PR, gönderim) yeniden göndermeden "
                        "önce gidip gitmediğine bak. Eksiği tamamla ve son cevabı baştan yaz.]",
                        f"\n\n[A cheaper tier tried this job; the manager review found it incomplete: {neden}\nIts result:\n"
                        f"{reply[:3000]}\nDon't redo what is done; before sending anything outward again (message, PR, "
                        "submission) check whether it already went. Finish what is missing and write the final reply anew.]")
            reply = None
    if reply is None and not durdu():
        reply = run(prompt, DEEP)
        adimlar.append({"kademe": "top", "model": DEEP})
    son = next((a["kademe"] for a in reversed(adimlar) if a["kademe"] != "review"), kademe)
    yaz({"no": no, "t": f"{datetime.now():%Y-%m-%d %H:%M}", "secim": secim, "gerekce": gerekce, "adimlar": adimlar,
         "son": son, "sn": int(time.monotonic() - t0), "tarif": tarif[:600]})
    return reply or ""


def yaz(kayit):
    try:
        KAYIT.parent.mkdir(parents=True, exist_ok=True)
        with KAYIT.open("a", encoding="utf-8") as f:
            f.write(json.dumps(kayit, ensure_ascii=False) + "\n")
    except OSError:
        pass  # the log is a gauge; a full disk must not lose the job's reply


def ozet(gun=7):
    """Tier split, escalations and their reasons over the last `gun` days."""
    sinir = f"{datetime.now() - timedelta(days=gun):%Y-%m-%d}"
    kayit = []
    if KAYIT.exists():
        for s in KAYIT.read_text(encoding="utf-8").splitlines():
            try:
                k = json.loads(s)
            except ValueError:
                continue
            if k.get("t", "") >= sinir:
                kayit.append(k)
    if not kayit:
        return T(f"Son {gun} günde kademe kaydı yok.", f"No routing records in the last {gun} days.")
    ucuz_ = sum(1 for k in kayit if k["son"] in ("cheap", "mid"))
    satir = [T(f"Son {gun} gün, {len(kayit)} iş. Seçim: {dict(Counter(k['secim'] for k in kayit))}. Bitiren: "
               f"{dict(Counter(k['son'] for k in kayit))}. Ucuz kademede biten: {ucuz_} (%{100 * ucuz_ // len(kayit)}).",
               f"Last {gun} days, {len(kayit)} jobs. Chosen: {dict(Counter(k['secim'] for k in kayit))}. Finished by: "
               f"{dict(Counter(k['son'] for k in kayit))}. Finished below top: {ucuz_} ({100 * ucuz_ // len(kayit)}%).")]
    for k in kayit:  # every job that reached the top tier and why: chosen directly or sent up by the review
        eksik = next((a.get("neden") for a in k["adimlar"] if a.get("karar") == "MISSING"), None)
        if k["son"] == "top":
            satir.append(f"  #{k.get('no')} top: " + (T(f"müdür eksik buldu ({eksik})", f"review found it incomplete ({eksik})")
                                                      if eksik else k["gerekce"]))
    return "\n".join(satir)
