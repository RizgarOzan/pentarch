"""Wiki keeper: a starter wiki for people who have none, and a nightly check of the one they have.

  python wiki.py kur [folder]     create a starter wiki (only in a folder with no .md files)
  python wiki.py tara [folder]    report broken links, orphans, missing frontmatter, stale pages (writes nothing)
  python wiki.py onar [folder]    harmless fixes only: missing frontmatter fields, unlisted pages into index
  python wiki.py yeniden [folder] [new]  build the recommended layout in a new folder (default <folder>-yeni) and a
                                  report of what moved where; the original is only read
Telegram (no model): `/ekle <note>` files a note under raw/telefon/, `/durum` shows the last scan. `/sor <question>`
goes to the model with an instruction to answer from the wiki.
The folder defaults to notes_dir. Nothing is ever deleted; content changes are left to the owner.
"""
import difflib
import json
import re
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

LINK = re.compile(r"\[\[([^\]|#^\\]+)")
CODE = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)
FIELDS = ("type", "domain", "tags", "updated")
FREE = {"index", "log", "overview"}  # pages that need no incoming link or Related line
MAX_BYTES = 32_000  # a bigger page should be split (Letta block limits, Claude Code memory cut-off)
CONTRA = re.compile(r"contradicts\s+\[\[([^\]|#]+)")  # typed relation on the Related line (basic-memory)
# recommended layout (Karpathy LLM wiki + PARA): page type -> folder; anything unknown goes to concepts
FOLDERS = ("entities", "concepts", "sources", "synthesis", "decisions", "archive")
TYPE_DIR = {**dict.fromkeys(("entity", "person", "project", "proje", "tool", "arac", "system"), "entities"),
            **dict.fromkeys(("source", "kaynak", "raw-transcript", "reference", "research", "arastirma"), "sources"),
            **dict.fromkeys(("synthesis", "analysis", "analiz", "ozet", "audit", "measurement", "hub", "moc"), "synthesis"),
            **dict.fromkeys(("decision", "plan"), "decisions")}
ROOT_TYPES = {"index", "log", "board", "meta", "rule"}

STARTER = {
    "tr": {
        "overview.md": ("meta", "# {owner} — genel bakış\n\nBu wiki {name} için kalıcı bellek. Yeni bir oturum önce bu sayfayı, "
                        "sonra [[index]] ve [[aktif-calismalar]] sayfalarını okur.\n\n## Ben kimim\n\n(adın, işin, hedeflerin: "
                        "{name} sohbetlerde öğrendikçe doldurur)\n\nRelated: [[index]] · [[wiki-protocol]]\n"),
        "index.md": ("meta", "# İndeks\n\nHer sayfa burada bir satırla listelenir.\n\n- [[overview]] — soğuk başlangıç özeti\n"
                     "- [[wiki-protocol]] — wiki nasıl okunur ve yazılır\n- [[aktif-calismalar]] — şu an kim neye dokunuyor\n"
                     "- [[log]] — değişiklik günlüğü\n"),
        "wiki-protocol.md": ("rule", "# Wiki protokolü\n\n- Bir sayfa = bir konu. Her sayfanın başında `type`, `domain`, `tags`, "
                             "`updated` alanları olur, sonunda bir `Related:` satırı.\n- Önemli bilgi silinmez, güncellenir. "
                             "Kaldırılacak şey önce `raw/` altına taşınır; `raw/` hiç düzenlenmez.\n- Ölçülen bir şey varsayımla "
                             "çelişirse sayıyla yazılır. Düzeltme sessizce üstüne yazılmaz, \"düzeltme:\" diye yazılır.\n"
                             "- Bir işe başlamadan [[aktif-calismalar]] sayfasına satır eklenir, bitince \"Son bitenler\"e taşınır.\n\n"
                             "Related: [[index]] · [[overview]]\n"),
        "aktif-calismalar.md": ("meta", "# Aktif çalışmalar\n\n| ne | kim | başladı |\n|---|---|---|\n\n## Son bitenler\n\n"
                                "Related: [[wiki-protocol]]\n"),
        "log.md": ("meta", "# Günlük\n\n- {today}: wiki {name} tarafından kuruldu.\n"),
    },
    "en": {
        "overview.md": ("meta", "# {owner} — overview\n\nThis wiki is the long-term memory of {name}. A new session reads this page "
                        "first, then [[index]] and [[active-work]].\n\n## Who I am\n\n(your name, work, goals: {name} fills this in "
                        "as it learns from your chats)\n\nRelated: [[index]] · [[wiki-protocol]]\n"),
        "index.md": ("meta", "# Index\n\nEvery page is listed here with one line.\n\n- [[overview]] — cold start summary\n"
                     "- [[wiki-protocol]] — how the wiki is read and written\n- [[active-work]] — who is touching what right now\n"
                     "- [[log]] — change log\n"),
        "wiki-protocol.md": ("rule", "# Wiki protocol\n\n- One page = one topic. Every page starts with `type`, `domain`, `tags`, "
                             "`updated` and ends with a `Related:` line.\n- Important facts are never deleted, only updated. "
                             "Anything removed moves to `raw/` first; `raw/` is never edited.\n- When a measurement contradicts an "
                             "assumption, write it with the number. A correction is written as \"correction:\", not silently.\n"
                             "- Add a row to [[active-work]] before starting, move it to \"Recently done\" when finished.\n\n"
                             "Related: [[index]] · [[overview]]\n"),
        "active-work.md": ("meta", "# Active work\n\n| what | who | started |\n|---|---|---|\n\n## Recently done\n\n"
                           "Related: [[wiki-protocol]]\n"),
        "log.md": ("meta", "# Log\n\n- {today}: wiki set up by {name}.\n"),
    },
}


def _root(folder):
    p = Path(folder).expanduser()
    return p / "wiki" if (p / "wiki").is_dir() else p


def _front(text):
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end < 0:
        return None, text
    head = {}
    for line in text[3:end].strip().splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            head[k.strip()] = v.strip()
    return head, text[end + 4:]


def kur(folder, owner="Owner", name="Pentarch", lang="en"):
    """Create the starter pages. Refuses (returns []) when the folder already holds markdown."""
    root = Path(folder).expanduser()
    if root.exists() and any(root.rglob("*.md")):
        return []
    (root / "wiki").mkdir(parents=True, exist_ok=True)
    (root / "raw").mkdir(exist_ok=True)
    for d in FOLDERS:
        (root / "wiki" / d).mkdir(exist_ok=True)
    today = date.today().isoformat()
    made = []
    for fname, (typ, body) in STARTER["tr" if lang == "tr" else "en"].items():
        text = f"---\ntype: {typ}\ndomain: meta\ntags: [wiki]\nupdated: {today}\n---\n\n" + body.format(owner=owner, name=name, today=today)
        (root / "wiki" / fname).write_text(text, encoding="utf-8")
        made.append(fname)
    return made


def tara(folder, stale_days=60):
    """Findings as a list of {kind, page, detail}. Writes nothing."""
    root = _root(folder)
    pages = {p.stem: p for p in root.rglob("*.md") if "raw" not in p.relative_to(root).parts}
    incoming = dict.fromkeys(pages, 0)
    superseded = set()
    out = []
    index_text = pages["index"].read_text(encoding="utf-8", errors="replace") if "index" in pages else ""
    for stem, p in pages.items():
        text = p.read_text(encoding="utf-8", errors="replace")
        head, body = _front(text)
        if len(text.encode("utf-8")) > MAX_BYTES:
            out.append({"kind": "too_big", "page": stem, "detail": f"{len(text.encode('utf-8')) // 1000} KB, split it"})
        for other in CONTRA.findall(body):
            out.append({"kind": "contradiction", "page": stem, "detail": f"contradicts [[{other.strip()}]]"})
        if head and head.get("superseded_by"):
            superseded.add(stem)
        if head is None:
            out.append({"kind": "frontmatter", "page": stem, "detail": "no frontmatter"})
        else:
            miss = [f for f in FIELDS if f not in head and not (f == "domain" and stem in FREE)]
            if miss:
                out.append({"kind": "frontmatter", "page": stem, "detail": "missing " + ", ".join(miss)})
            try:
                age = (date.today() - datetime.strptime(head.get("updated", "")[:10], "%Y-%m-%d").date()).days
                if age > stale_days:
                    out.append({"kind": "stale", "page": stem, "detail": f"{age} days since update"})
            except ValueError:
                pass
        for target in {t.strip() for t in LINK.findall(CODE.sub("", body))}:
            key = Path(target).stem
            if key in pages:
                if key != stem:
                    incoming[key] += 1
            else:
                out.append({"kind": "broken_link", "page": stem, "detail": f"[[{target}]]"})
        if stem not in FREE and "Related" not in body:
            out.append({"kind": "related", "page": stem, "detail": "no Related line"})
        if index_text and stem not in FREE and f"[[{stem}" not in index_text:
            out.append({"kind": "unindexed", "page": stem, "detail": "not in index"})
    names = sorted(k for k in pages if k not in FREE)
    for i, a in enumerate(names):  # search before creating (basic-memory, mem0): near-identical names are likely duplicates
        for b in names[i + 1:i + 40]:
            if difflib.SequenceMatcher(None, a, b).ratio() > 0.88:
                out.append({"kind": "duplicate", "page": a, "detail": f"looks like [[{b}]]"})
    for stem, p in pages.items():
        if stem not in superseded:
            for t in {t.strip() for t in LINK.findall(CODE.sub("", p.read_text(encoding="utf-8", errors="replace")))}:
                if t in superseded and t != stem:
                    out.append({"kind": "superseded_link", "page": stem, "detail": f"links old page [[{t}]]"})
    out += [{"kind": "orphan", "page": k, "detail": "no page links here"} for k, n in incoming.items() if n == 0 and k not in FREE]
    return out


def onar(folder):
    """Harmless fixes only: fill missing frontmatter fields, list unindexed pages at the end of index. Returns what changed."""
    root = _root(folder)
    done = []
    defaults = {"type": "note", "domain": "general", "tags": "[]", "updated": date.today().isoformat()}
    for f in tara(folder):
        if f["kind"] != "frontmatter":
            continue
        p = next(root.rglob(f["page"] + ".md"))
        text = p.read_text(encoding="utf-8")
        head, body = _front(text)
        if head is None:
            new = "---\n" + "".join(f"{k}: {v}\n" for k, v in defaults.items()) + "---\n\n" + text
        else:  # keep the original block as written, append the missing keys before its closing line
            end = text.find("\n---", 3)
            extra = "".join(f"\n{k}: {defaults[k]}" for k in FIELDS if k not in head and not (k == "domain" and f["page"] in FREE))
            new = text[:end] + extra + text[end:]
        p.write_text(new, encoding="utf-8")
        done.append(f"{f['page']}: frontmatter")
    missing = [f["page"] for f in tara(folder) if f["kind"] == "unindexed"]
    idx = root / "index.md"
    if missing and idx.exists():
        head = "" if "## Sonra yerleşecek" in idx.read_text(encoding="utf-8") else "\n## Sonra yerleşecek\n\n"
        with idx.open("a", encoding="utf-8") as fh:
            fh.write(head + "".join(f"- [[{m}]]\n" for m in missing))
        done.append(f"index: +{len(missing)}")
    return done


def yeniden(folder, new=None):
    """Copy every page into the recommended layout in a new folder and write RAPOR.md there. The original is only
    read; an existing target is refused. Returns the report path, or None."""
    src = Path(folder).expanduser()
    dst = Path(new).expanduser() if new else src.with_name(src.name + "-yeni")
    if dst.exists():
        return None
    wroot = _root(src)
    for d in FOLDERS:
        (dst / "wiki" / d).mkdir(parents=True, exist_ok=True)
    if (src / "raw").is_dir():
        shutil.copytree(src / "raw", dst / "raw")
    moved, clash, before = {}, [], tara(src)
    for p in sorted(wroot.rglob("*.md")):
        if "raw" in p.relative_to(wroot).parts:
            continue
        head, _ = _front(p.read_text(encoding="utf-8", errors="replace"))
        typ = (head or {}).get("type", "").lower()
        if p.stem in FREE or typ in ROOT_TYPES or p.stem in ("wiki-protocol", "aktif-calismalar", "active-work"):
            sub = ""
        elif (head or {}).get("superseded_by"):
            sub = "archive"
        else:
            sub = TYPE_DIR.get(typ, "concepts")
        target = dst / "wiki" / sub / p.name
        if target.exists():  # same name twice: keep both, wikilinks by name would be ambiguous
            target = target.with_name(f"{p.stem}--{p.parent.name}.md")
            clash.append(p.stem)
        shutil.copy2(p, target)
        moved.setdefault(sub or "(kök)", []).append(p.stem)
    count_src = sum(1 for p in wroot.rglob("*.md") if "raw" not in p.relative_to(wroot).parts)
    count_dst = sum(len(v) for v in moved.values())
    after = tara(dst)
    lines = [f"# Yeniden kurulum raporu ({date.today().isoformat()})", "", f"Kaynak: {src} (dokunulmadı)", "",
             f"Sayfa: {count_src} → {count_dst}" + ("" if count_src == count_dst else "  ⚠ EKSİK VAR, geçme"), "",
             "## Nereye gitti", ""] + [f"- **{k}**: {len(v)}" for k, v in sorted(moved.items())]
    if clash:
        lines += ["", "## Aynı adlı sayfalar (ikisi de tutuldu, birleştirmeye karar ver)", ""] + [f"- {c}" for c in clash]
    lines += ["", "## Bulgular: önce → sonra", "", "```", ozet(before), "---", ozet(after), "```", "",
              "Geçmek için eski klasörü yedekleyip yenisini onun yerine koy. Bunu Pentarch kendisi yapmaz."]
    (dst / "RAPOR.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dst / "RAPOR.md"


def ekle(folder, text):
    """A note from the phone: appended to raw/telefon/<date>.md with the time. The nightly round files it."""
    f = Path(folder).expanduser() / "raw" / "telefon" / f"{date.today().isoformat()}.md"
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as out:
        out.write(f"- {datetime.now():%H:%M} {text.strip()}\n")
    return f


def komut(text, folder):
    """Wiki commands that need no model. Returns the reply, or None when the message isn't one."""
    t = text.strip()
    if m := re.fullmatch(r"/(?:ekle|add)\s+(.+)", t, re.S):
        f = ekle(folder, m.group(1))
        from config import T
        return T(f"Eklendi: raw/telefon/{f.name}. Gece wiki'ye işlenir.", f"Added: raw/telefon/{f.name}. Filed into the wiki tonight.")
    if re.fullmatch(r"/(?:durum|status)", t):
        return ozet(tara(folder))
    return None


def soru(text):
    """`/sor x` becomes a prompt that keeps the answer to the wiki; any other text comes back unchanged."""
    m = re.fullmatch(r"\s*/(?:sor|ask)\s+(.+)", text, re.S)
    return (f"Answer from the wiki in the notes folder only: search it, read the pages you need and name them as "
            f"[[page]] after each claim. If the wiki doesn't say, say so in one line. Question: {m.group(1)}") if m else text


def yedek(folder):
    """Nightly: if the notes folder is a git repo, commit what changed and push when there is a remote. Never forces."""
    import subprocess
    f = Path(folder).expanduser()
    if not (f / ".git").exists() or not subprocess.run(["git", "-C", str(f), "remote"], capture_output=True,
                                                         text=True).stdout.strip():
        return "-"  # only a folder setup.py (or the owner) connected to a remote
    run = lambda *a: subprocess.run(["git", "-C", str(f), *a], capture_output=True, text=True,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    run("add", "-A")
    made = run("commit", "-q", "-m", f"wiki {date.today().isoformat()}").returncode == 0
    return "push ok" if run("push", "-q").returncode == 0 else ("push failed" if made else "-")


def ozet(findings):
    """One short report line per kind."""
    by = {}
    for f in findings:
        by.setdefault(f["kind"], []).append(f["page"])
    return "\n".join(f"{k}: {len(v)} ({', '.join(sorted(v)[:5])}{'…' if len(v) > 5 else ''})" for k, v in sorted(by.items())) or "-"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "tara"
    from config import C, NAME, NOTES, OWNER  # noqa: E402
    folder = sys.argv[2] if len(sys.argv) > 2 else NOTES
    if cmd == "kur":
        print(json.dumps(kur(folder, OWNER, NAME, C.get("lang", "en")), ensure_ascii=False))
    elif cmd == "yeniden":
        print(yeniden(folder, sys.argv[3] if len(sys.argv) > 3 else None) or "hedef klasör zaten var, dokunmadım")
    elif cmd == "yedek":
        print(yedek(folder))
    elif cmd == "ekle":
        print(ekle(folder, " ".join(sys.argv[3:])))
    elif cmd == "onar":
        print("\n".join(onar(folder)) or "-")
    else:
        print(ozet(tara(folder)))
