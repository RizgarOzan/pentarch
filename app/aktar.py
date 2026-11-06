"""Import instructions and skills from Claude Code and Codex into the Pentarch runtime home. Sources are only read.

  python -I aktar.py            # what would be imported (nothing written)
  python -I aktar.py --yaz      # write it

- Instructions (~/.claude/CLAUDE.md, ~/.codex/AGENTS.md) go to <home>/aktarilan-talimatlar.md, a page for you to
  merge into sistem.md / kurallar.md by hand; they are not injected on their own.
- Skills (~/.claude/skills/*/SKILL.md, ~/.codex/skills/*/SKILL.md) get a pointer skill in <home>/beceriler/<name>/SKILL.md
  (agentskills.io layout, same name and description) that tells the agent to read the original.
Text that looks like a prompt injection or exfiltration (ogren.tara) is skipped and logged.
"""
import re
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


def kaynaklar(ev=Path.home()):
    talimat = [p for p in (ev / ".claude" / "CLAUDE.md", ev / ".codex" / "AGENTS.md") if p.exists()]
    beceri = sorted(p for kok in (ev / ".claude" / "skills", ev / ".codex" / "skills") if kok.exists()
                    for p in kok.glob("*/SKILL.md"))
    return talimat, beceri


def aktar(ev=Path.home(), hedef=HOME, yaz=False):
    """Returns report lines; with yaz=True also writes. Never touches the source files."""
    talimat, beceri = kaynaklar(ev)
    rapor, parcalar = [], []
    for p in talimat:
        metin = p.read_text(encoding="utf-8", errors="replace")
        if neden := ogren.tara(metin):
            ogren.reddet_log("aktar", f"{p}: {metin[:200]}", neden)
            rapor.append(T(f"atlandı ({neden}): {p}", f"skipped ({neden}): {p}"))
            continue
        parcalar.append(f"## {p}\n\n{metin.strip()}\n")
        rapor.append(T(f"talimat: {p}", f"instructions: {p}"))
    for p in beceri:
        meta, sorun = skill_meta(p.read_text(encoding="utf-8", errors="replace"), p.parent.name)
        ad = meta.get("name") if meta.get("name") and AD_RE.match(meta["name"]) else p.parent.name.lower()
        acik = (meta.get("description") or ad).replace("\n", " ")[:1024]
        if neden := ogren.tara(acik):
            ogren.reddet_log("aktar", f"{p}: {acik}", neden)
            rapor.append(T(f"atlandı ({neden}): {p}", f"skipped ({neden}): {p}"))
            continue
        rapor.append(f"skill {ad}: {p}" + (f"  ({'; '.join(sorun)})" if sorun else ""))
        if yaz:
            d = hedef / "beceriler" / ad
            d.mkdir(parents=True, exist_ok=True)
            (d / "SKILL.md").write_text(f"---\nname: {ad}\ndescription: {acik}\n---\n\nRead and follow {p}\n",
                                        encoding="utf-8")
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
