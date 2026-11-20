"""Import instructions, memory, skills and scheduled jobs from Claude Code, Codex, Hermes Agent and OpenClaw into the
Pentarch runtime home. Sources are only read; .env, auth.json, credentials and config files are never opened.

  python -I aktar.py            # what would be imported (nothing written)
  python -I aktar.py --yaz      # write it

- Instructions (~/.claude/CLAUDE.md, ~/.codex/AGENTS.md) go to <home>/aktarilan-talimatlar.md, a page for you to
  merge into sistem.md / kurallar.md by hand; they are not injected on their own.
- Skills (~/.claude/skills/*/SKILL.md, ~/.codex/skills/*/SKILL.md) are copied to <home>/beceriler/<name>/ (agentskills.io
  layout, same name and description; a folder over 5 MB gets a pointer to the original instead).
- Hermes (~/.hermes or $HERMES_HOME): SOUL.md goes to the same page; memories/USER.md, MEMORY.md entries go into
  memory.md one by one; skills/**/SKILL.md are copied, and cron/jobs.json becomes ready `routine add` commands on that
  page (never added on their own).
- OpenClaw (~/.openclaw/workspace): AGENTS.md, SOUL.md, IDENTITY.md, USER.md, MEMORY.md and both skills folders.
Text that looks like a prompt injection or exfiltration (ogren.tara) is skipped and logged.
"""
import json
import os
import re
import shlex
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ogren  # noqa: E402
from config import HOME, T  # noqa: E402

AD_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
ALANLAR = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}


def skill_meta(text, klasor=None):
    """SKILL.md frontmatter per agentskills.io: (fields, problems). Simple `key: value` lines; metadata's indented
    `k: v` lines become a dict. Problems list what breaks the spec (name/description rules, unknown fields)."""
    m = re.match(r"\A---\r?\n(.*?)\r?\n---", text or "", re.S)
    if not m:
        return {}, ["no frontmatter"]
    meta, son = {}, None
    for satir in m.group(1).splitlines():
        if satir.startswith((" ", "\t")) and son == "metadata" and ":" in satir:
            k, _, v = satir.strip().partition(":")
            meta["metadata"][k.strip()] = v.strip().strip("'\"")
        elif satir.startswith((" ", "\t")) and isinstance(meta.get(son), str) and satir.strip():
            # YAML block scalar (`description: >` followed by indented lines): join the lines
            meta[son] = (re.sub(r"^[>|][-+]?$", "", meta[son]) + " " + satir.strip()).strip()
        elif ":" in satir and not satir.startswith((" ", "\t", "#")):
            k, _, v = satir.partition(":")
            son = k.strip()
            meta[son] = {} if son == "metadata" and not v.strip() else v.strip().strip("'\"")
    sorun = []
    ad, acik = meta.get("name", ""), meta.get("description", "")
    if not ad or len(ad) > 64 or not AD_RE.match(ad):
        sorun.append("name: 1-64 lowercase letters, digits and single hyphens")
    elif klasor and ad != klasor:
        sorun.append(f"name '{ad}' differs from folder '{klasor}'")
    if not acik or len(acik) > 1024:
        sorun.append("description: required, at most 1024 characters")
    if len(meta.get("compatibility", "")) > 500:
        sorun.append("compatibility: at most 500 characters")
    sorun += [f"unknown field: {k}" for k in meta if k not in ALANLAR]
    return meta, sorun


def _yerler(ev, env):
    """Hermes Agent and OpenClaw homes. Env overrides count only for the real home, so a test tree stays isolated."""
    if env is None:
        env = os.environ if ev == Path.home() else {}
    hermes = [Path(env["HERMES_HOME"])] if env.get("HERMES_HOME") else [ev / ".hermes", ev / "AppData" / "Local" / "hermes"]
    claw = Path(env.get("OPENCLAW_STATE_DIR") or ev / ".openclaw")
    return [h for h in hermes if h.is_dir()], claw, Path(env.get("OPENCLAW_WORKSPACE_DIR") or claw / "workspace")


def kaynaklar(ev=Path.home(), env=None):
    """(instruction files, skill files, Hermes cron files). Never reads .env, auth.json, credentials or config."""
    hermes, claw, alan = _yerler(ev, env)
    talimat = [ev / ".claude" / "CLAUDE.md", ev / ".codex" / "AGENTS.md"]
    for h in hermes:
        talimat += [h / "SOUL.md", h / "memories" / "USER.md", h / "memories" / "MEMORY.md"]
    talimat += [alan / f for f in ("AGENTS.md", "SOUL.md", "IDENTITY.md", "USER.md", "MEMORY.md")]
    kokler = [(ev / ".claude" / "skills", "*/SKILL.md"), (ev / ".codex" / "skills", "*/SKILL.md")]
    kokler += [(h / "skills", "**/SKILL.md") for h in hermes]  # Hermes nests skills under category folders
    kokler += [(claw / "skills", "**/SKILL.md"), (alan / "skills", "**/SKILL.md")]
    beceri = sorted({p for kok, desen in kokler if kok.is_dir() for p in kok.glob(desen)})
    return ([p for p in talimat if p.is_file()], beceri,
            [h / "cron" / "jobs.json" for h in hermes if (h / "cron" / "jobs.json").is_file()])


GUNLER = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]


def rutin_zamani(s):
    """A Hermes schedule ('every 2h', 'every 1d at 09:00', '30 9 * * 1-5') as a Pentarch routine time, or None.
    Intervals outside the 15-1440 minutes a routine allows give None too."""
    s = (s or "").strip().lower()
    dk = None
    if m := re.fullmatch(r"every\s+(\d+)\s*(m|mins?|minutes?|h|hrs?|hours?|d|days?)", s):
        dk = int(m.group(1)) * {"m": 1, "h": 60, "d": 1440}[m.group(2)[0]]
    elif m := re.fullmatch(r"\*/(\d+)\s+\*\s+\*\s+\*\s+\*", s):
        dk = int(m.group(1))
    elif m := re.fullmatch(r"0\s+\*/(\d+)\s+\*\s+\*\s+\*", s):
        dk = int(m.group(1)) * 60
    if dk is not None:
        return f"{dk}m@00:00-23:59" if 15 <= dk <= 1440 else None  # Hermes runs these at night too
    if m := re.fullmatch(r"every\s+(?:1\s*d|day)\s+at\s+(\d{1,2}):(\d\d)", s):
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    if m := re.fullmatch(r"(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+\*\s+\*", s):  # monthly: minute hour day-of-month
        dk, sa, gun = map(int, m.groups())
        return f"{gun}@{sa:02d}:{dk:02d}" if dk <= 59 and sa <= 23 and 1 <= gun <= 31 else None
    if not (m := re.fullmatch(r"(\d{1,2})\s+(\d{1,2})\s+\*\s+\*\s+(\S+)", s)):
        return None
    dk, sa, gun = int(m.group(1)), int(m.group(2)), m.group(3)
    if dk > 59 or sa > 23:
        return None
    if gun == "*":
        return f"{sa:02d}:{dk:02d}"
    secilen = set()
    for parca in gun.split(","):
        a, _, b = parca.partition("-")
        try:
            ia = int(a) if a.isdigit() else GUNLER.index(a[:3])
            ib = (int(b) if b.isdigit() else GUNLER.index(b[:3])) if b else ia
        except ValueError:
            return None
        secilen |= {i % 7 for i in range(ia, ib + 1)}
    return ",".join(GUNLER[i] for i in sorted(secilen, key=lambda i: (i + 6) % 7)) + f"@{sa:02d}:{dk:02d}"


def cron_isleri(dosya):
    """Hermes jobs.json -> [(name, schedule, prompt, routine time or None, enabled)]."""
    try:
        veri = json.loads(dosya.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out, alinan = [], set()
    for j in (veri.get("jobs", []) if isinstance(veri, dict) else veri if isinstance(veri, list) else []):
        if not isinstance(j, dict) or not str(j.get("prompt") or "").strip():
            continue
        ad = _benzersiz(re.sub(r"[^a-z0-9]+", "-", str(j.get("name") or j.get("id") or "hermes").lower()).strip("-")[:40]
                        or "hermes", alinan)
        sch = j.get("schedule") or ""
        if isinstance(sch, dict):  # newer Hermes may store {"kind": ..., "expr"/"display": ...}
            sch = sch.get("expr") or sch.get("display") or sch.get("value") or ""
        out.append((ad, str(sch), str(j["prompt"]).strip()[:1500], rutin_zamani(str(sch)), j.get("enabled", True) is not False))
    return out


def _benzersiz(ad, alinan):
    """Two jobs or skills with the same name would overwrite each other: the second becomes name-2."""
    yeni, i = ad, 2
    while yeni in alinan:
        yeni, i = f"{ad}-{i}", i + 1
    alinan.add(yeni)
    return yeni


def _tirnak(s):
    """Quote for the shell the owner will paste into: PowerShell on Windows, sh elsewhere. The job goes on one line,
    and double quotes become single ones, since Windows PowerShell 5.1 drops a `"` inside an argument it hands to python."""
    s = " ".join(s.replace('"', "'").split())
    return "'" + s.replace("'", "''") + "'" if os.name == "nt" else shlex.quote(s)


def _girdiler(metin):
    """Hermes memory entries are separated by a line holding only '§'."""
    return [e.strip() for e in re.split(r"(?m)^[ \t]*§[ \t]*$", metin) if e.strip()]


def aktar(ev=Path.home(), hedef=HOME, yaz=False, env=None):
    """Returns report lines; with yaz=True also writes. Never touches the source files. Memory entries are checked one
    by one and the clean ones queued for memory.md (written by Pentarch at its next start, hafiza-kuyruk.jsonl)."""
    talimat, beceri, cronlar = kaynaklar(ev, env)
    rapor, parcalar, hafiza = [], [], []
    for p in talimat:
        metin = p.read_text(encoding="utf-8", errors="replace")
        if p.parent.name == "memories":
            temiz = []
            for e in _girdiler(metin):
                if neden := ogren.tara(e):
                    ogren.reddet_log("aktar", f"{p}: {e[:200]}", neden)
                    rapor.append(T(f"atlandı ({neden}): {p}: {e[:60]}", f"skipped ({neden}): {p}: {e[:60]}"))
                else:
                    temiz.append(e)
            hafiza += [" ".join(e.split()) for e in temiz]
            rapor.append(T(f"hafıza: {p} ({len(temiz)} girdi)", f"memory: {p} ({len(temiz)} entries)"))
            continue
        if neden := ogren.tara(metin):
            ogren.reddet_log("aktar", f"{p}: {metin[:200]}", neden)
            rapor.append(T(f"atlandı ({neden}): {p}", f"skipped ({neden}): {p}"))
            continue
        parcalar.append(f"## {p}\n\n{metin.strip()}\n")
        rapor.append(T(f"talimat: {p}", f"instructions: {p}"))
    if yaz and hafiza:
        with (hedef / "hafiza-kuyruk.jsonl").open("a", encoding="utf-8") as f:
            for e in hafiza:
                f.write(json.dumps({"bolum": ["Lessons", "Dersler", "Status", "Durum"], "satir": e[:500]}, ensure_ascii=False) + "\n")
    komutlar = []
    for dosya in cronlar:
        for ad, sch, istem, ne_zaman, acik in cron_isleri(dosya):
            if neden := ogren.tara(istem):
                ogren.reddet_log("aktar", f"{dosya} {ad}: {istem[:200]}", neden)
                rapor.append(T(f"atlandı ({neden}): Hermes işi {ad}", f"skipped ({neden}): Hermes job {ad}"))
                continue
            durum = "" if acik else T(" (Hermes'te duraklatılmış)", " (paused in Hermes)")
            if not acik:
                komutlar.append(T(f"# {ad}: Hermes'te duraklatılmış", f"# {ad}: paused in Hermes"))
            if ne_zaman:
                komutlar.append(f"python -I app/pentarch.py {T('rutin ekle', 'routine add')} {ad} {ne_zaman} {_tirnak(istem)}")
                rapor.append(T(f"rutin önerisi {ad} ({sch} -> {ne_zaman}){durum}", f"routine suggestion {ad} ({sch} -> {ne_zaman}){durum}"))
            else:
                komutlar.append(T(f"# {ad}: '{sch}' çevrilemedi (rutinler HH:MM, gün@HH:MM ya da 15-1440 dakikada bir çalışır), "
                                  "elle zaman ver: ", f"# {ad}: '{sch}' has no direct match (routines take HH:MM, day@HH:MM or "
                                  "every 15-1440 minutes), pick a time: ") + _tirnak(istem))
                rapor.append(T(f"rutin önerisi {ad}: '{sch}' elle çevrilmeli{durum}", f"routine suggestion {ad}: '{sch}' needs a time by hand{durum}"))
    if komutlar:
        parcalar.append(T("## Hermes zamanlanmış işleri\n\nOtomatik eklenmedi. İstediğini çalıştır (aynı işi iki araç birden "
                          "yapmasın diye Hermes'te durdur):\n\n", "## Hermes scheduled jobs\n\nNot added on their own. Run the "
                          "ones you want (and pause them in Hermes so both tools don't do the same job):\n\n")
                        + "```\n" + "\n".join(komutlar) + "\n```\n")
    alinan = set()
    for p in beceri:
        meta, sorun = skill_meta(p.read_text(encoding="utf-8", errors="replace"), p.parent.name)
        ad = meta.get("name") if meta.get("name") and AD_RE.match(meta["name"]) else p.parent.name.lower()
        if (yeni := _benzersiz(ad, alinan)) != ad:
            sorun.append(T(f"aynı adlı başka beceri var, {yeni} adıyla", f"another skill has this name, saved as {yeni}"))
            ad = yeni
        acik = (meta.get("description") or ad).replace("\n", " ")[:1024]
        govde = re.sub(r"\A---\n.*?\n---\n?", "", p.read_text(encoding="utf-8", errors="replace"), flags=re.S).strip()
        if neden := ogren.tara(acik) or ogren.tara(govde):  # the body is what the agent will follow, so it is checked too
            ogren.reddet_log("aktar", f"{p}: {acik}", neden)
            rapor.append(T(f"atlandı ({neden}): {p}", f"skipped ({neden}): {p}"))
            continue
        ekler = [f for f in p.parent.rglob("*") if f.is_file() and f != p]
        if ekler:
            sorun.append(T(f"{len(ekler)} ek dosya kopyalandı, bir göz at", f"{len(ekler)} extra files copied, give them a look"))
        rapor.append(f"skill {ad}: {p}" + (f"  ({'; '.join(sorun)})" if sorun else ""))
        if yaz:  # a copy, so the skill keeps working if ~/.hermes is moved or removed
            d = hedef / "beceriler" / ad
            if sum(f.stat().st_size for f in ekler) <= 5_000_000:
                shutil.copytree(p.parent, d, dirs_exist_ok=True)
            else:
                d.mkdir(parents=True, exist_ok=True)
                govde += f"\n\n(Files of this skill: {p.parent})"
            (d / "SKILL.md").write_text(f"---\nname: {ad}\ndescription: {acik}\n---\n\n{govde}\n", encoding="utf-8")
    if yaz and parcalar:
        (hedef / "aktarilan-talimatlar.md").write_text(
            T("# Aktarılan talimatlar\n\nElle sistem.md / kurallar.md içine taşı; kendiliğinden kullanılmaz.\n\n",
              "# Imported instructions\n\nMove what you want into sistem.md / kurallar.md; not used on its own.\n\n")
            + "\n".join(parcalar), encoding="utf-8")
    return rapor or [T("aktarılacak bir şey bulunamadı", "nothing to import found")]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    yaz = "--yaz" in sys.argv or "--write" in sys.argv
    print("\n".join(aktar(yaz=yaz)))
    if not yaz:
        print(T("(yazılmadı; yazmak için --yaz)", "(nothing written; add --write to write)"))


if __name__ == "__main__":
    main()
