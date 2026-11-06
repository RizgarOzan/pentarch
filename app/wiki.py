"""Wiki keeper: a starter wiki for people who have none, and a nightly check of the one they have.

  python wiki.py kur [folder]     create a starter wiki (only in a folder with no .md files)
  python wiki.py tara [folder]    report broken links, orphans, missing frontmatter, stale pages (writes nothing)
  python wiki.py onar [folder]    harmless fixes only: missing frontmatter fields, unlisted pages into index
The folder defaults to notes_dir. Nothing is ever deleted; content changes are left to the owner.
"""
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

LINK = re.compile(r"\[\[([^\]|#^\\]+)")
CODE = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)
FIELDS = ("type", "domain", "tags", "updated")
FREE = {"index", "log", "overview"}  # pages that need no incoming link or Related line

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
    out = []
    index_text = pages["index"].read_text(encoding="utf-8", errors="replace") if "index" in pages else ""
    for stem, p in pages.items():
        head, body = _front(p.read_text(encoding="utf-8", errors="replace"))
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
    elif cmd == "onar":
        print("\n".join(onar(folder)) or "-")
    else:
        print(ozet(tara(folder)))
