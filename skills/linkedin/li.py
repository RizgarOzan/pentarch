# -*- coding: utf-8 -*-
"""LinkedIn helper for the Pentarch skills. Standard library only. Nothing here talks to LinkedIn.

    python li.py check post.txt                  fold preview, length, format and wording checks
    python li.py profile profile.json            score a profile export against the /100 rubric
    python li.py log add --hook "Number Reveal" --pillar authority --file post.txt
    python li.py log result 3 --views 1200 --comments 8 [--reactions 40]
    python li.py log stats                       reach per hook formula and per pillar
    python li.py network add --name "A. B." --company X --why "hiring manager" [--days 7]
    python li.py network touch 2 [--days 14]     record a contact, push the next follow-up
    python li.py network due                     follow-ups that are due today or overdue

State lives in ~/.pentarch/linkedin/ (log.json, network.json). --home DIR overrides that.
Exit code 1 when a check FAILs, else 0.
"""
import argparse, datetime, json, os, pathlib, re, sys

HOOK_CHARS = 210        # about where "...see more" cuts a desktop feed post; convention, varies by device
SOFT_MAX, HARD_MAX = 1300, 3000   # 3,000 is the LinkedIn post limit; 1,300 is a convention

# phrases that mark text as generated; matched case-insensitively, EN and TR
AI_TELLS = [
    "delve", "game-changer", "game changer", "in today's fast-paced", "i'm thrilled to announce", "thrilled to share",
    "excited to share", "excited to announce", "humbled to", "unlock your", "unlock the", "navigate the", "landscape",
    "leverage", "elevate", "empower", "journey", "testament to", "tapestry", "it's not just", "it's not about",
    "let that sink in", "read that again", "here's the thing", "the real question", "at its core", "in a world where",
    "buckle up", "dive in", "deep dive", "robust", "seamless", "synergy", "paradigm", "revolutionize", "cutting-edge",
    "heyecanla paylaşıyorum", "paylaşmaktan mutluluk duyuyorum", "bir yolculuk", "yolculuğumda", "mükemmel bir fırsat",
    "bu vesileyle", "fırsat buldum", "inanılmaz bir deneyim", "sizlerle paylaşmak istiyorum", "harika bir ekip",
]
# word -> plainer word
REPLACE = {
    "utilize": "use", "leverage": "use", "commence": "start", "endeavor": "try", "facilitate": "help", "optimal": "best",
    "implement": "build", "showcase": "show", "foster": "build", "robust": "solid", "seamless": "smooth",
    "gerçekleştirmek": "yapmak", "bünyesinde": "-de", "vesilesiyle": "ile", "adına": "için", "ivme kazandırmak": "hızlandırmak",
}


def home(path=None):
    if path:
        p = pathlib.Path(path).expanduser()
    else:
        p = pathlib.Path(os.environ.get("PENTARCH_HOME") or pathlib.Path.home() / ".pentarch").expanduser() / "linkedin"
    p.mkdir(parents=True, exist_ok=True)
    return p


def load(p, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def save(p, obj):
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------- check ----------
def check_text(text):
    """Returns a list of (level, message); level is PASS, WARN or FAIL."""
    out, t = [], text.strip()
    hook = t[:HOOK_CHARS].split("\n\n")[0].strip()
    out.append(("INFO", f"fold preview ({len(hook)} chars): {hook!r}"))
    first = t.split("\n")[0]
    if len(first) > HOOK_CHARS:
        out.append(("WARN", f"first line is {len(first)} chars; the feed cuts around {HOOK_CHARS}, so the hook ends mid-sentence"))
    if len(hook) < 30:
        out.append(("WARN", "hook under 30 chars; it carries the whole click"))
    elif re.search(r"\d|\?", hook) or re.search(r"\b(no|not|never|stop|wrong|hayır|değil|asla|yanlış)\b", hook, re.I):
        out.append(("PASS", "hook has a number, a question or a contrast"))
    else:
        out.append(("WARN", "hook has no number, question or contrast; check it against the formula list"))
    n = len(t)
    if n > HARD_MAX:
        out.append(("FAIL", f"{n} chars; LinkedIn cuts posts at {HARD_MAX}"))
    elif n > SOFT_MAX:
        out.append(("WARN", f"{n} chars; over the {SOFT_MAX} convention, trim unless every line earns it"))
    else:
        out.append(("PASS", f"{n} chars"))
    paras = [p for p in re.split(r"\n\s*\n", t) if p.strip()]
    long = [p for p in paras if len(p) > 300]
    if len(paras) == 1 and n > 400:
        out.append(("WARN", "one block of text; put a blank line between thoughts"))
    elif long:
        out.append(("WARN", f"{len(long)} paragraph(s) over 300 chars; split them"))
    else:
        out.append(("PASS", f"{len(paras)} short paragraphs"))
    if re.search(r"https?://|www\.", t):
        out.append(("WARN", "link in the body; put it in the first comment (convention, reach effect unverified)"))
    tags = re.findall(r"(?<!\w)#\w+", t)
    out.append(("PASS" if len(tags) <= 3 else "WARN", f"{len(tags)} hashtags" + ("" if len(tags) <= 3 else "; keep 0-3")))
    last = [l for l in t.split("\n") if l.strip()][-1] if t else ""
    out.append(("PASS" if last.rstrip().endswith("?") else "WARN", "ends with a question" if last.rstrip().endswith("?") else "does not end with a question; give readers something to answer"))
    low = t.lower()
    tells = [p for p in AI_TELLS if p in low]
    if "—" in t or "–" in t:
        tells.append("em dash")
    if re.search(r"\bnot\b[^.\n]{0,60}\bbut\b", low) or re.search(r"\bdeğil\b[^.\n]{0,60}\b(ama|aksine)\b", low):
        tells.append("not X but Y")
    out.append(("PASS", "no AI-tell phrases") if not tells else ("WARN", "AI tells: " + ", ".join(tells)))
    swaps = [f"{k} -> {v}" for k, v in REPLACE.items() if re.search(r"(?<!\w)" + re.escape(k) + r"(?!\w)", low)]
    if swaps:
        out.append(("WARN", "plainer words: " + "; ".join(swaps)))
    emoji = len(re.findall(r"[\U0001F300-\U0001FAFF☀-➿]", t))
    if emoji > 3:
        out.append(("WARN", f"{emoji} emoji; a few is plenty"))
    return out


# ---------- profile ----------
RUBRIC = [  # (key, max points, description)
    ("headline", 12, "headline: what you do + who for + a result, under 220 chars"),
    ("about_open", 10, "About opens with a hook in the first 265 chars (the fold)"),
    ("about_body", 10, "About body 150-300 words with at least one number"),
    ("featured", 8, "3 Featured items"),
    ("banner", 6, "custom banner (1584x396)"),
    ("photo", 6, "photo at 400px or larger"),
    ("current_role", 10, "current role has 2+ bullets with a verb and a number"),
    ("experience_depth", 8, "every experience entry has at least one bullet"),
    ("skills", 6, "20+ skills with the top 3 pinned"),
    ("recommendations", 8, "3+ recommendations"),
    ("activity", 10, "4+ posts or 20+ comments in the last 30 days"),
    ("contact", 6, "custom URL and a contact channel set"),
]


def score_profile(p):
    """p: dict exported by hand (see linkedin-profile SKILL.md). Returns (total, [(key, got, max, note)])."""
    rows = []
    hl = p.get("headline") or ""
    has_num = lambda s: bool(re.search(r"\d", s or ""))
    def row(key, got, note=""):
        mx = dict((k, m) for k, m, _ in RUBRIC)[key]
        rows.append((key, min(got, mx), mx, note))
    row("headline", (6 if hl else 0) + (3 if 0 < len(hl) <= 220 else 0) + (3 if "|" in hl or has_num(hl) else 0), f"{len(hl)} chars")
    about = p.get("about") or ""
    first = about[:265]
    row("about_open", (5 if first else 0) + (5 if re.search(r"\d|\?", first) else 0), f"first 265 chars: {first[:60]!r}")
    words = len(about.split())
    row("about_body", (5 if 150 <= words <= 300 else 2 if words else 0) + (5 if has_num(about) else 0), f"{words} words")
    row("featured", min(3, int(p.get("featured") or 0)) * 8 // 3, f"{p.get('featured', 0)} items")
    row("banner", 6 if p.get("banner") else 0)
    row("photo", 6 if int(p.get("photo_px") or 0) >= 400 else 3 if p.get("photo_px") else 0)
    exp = p.get("experience") or []
    cur = exp[0].get("bullets", []) if exp else []
    row("current_role", min(2, len([b for b in cur if has_num(b)])) * 5, f"{len(cur)} bullets, {len([b for b in cur if has_num(b)])} with a number")
    row("experience_depth", 8 if exp and all(e.get("bullets") for e in exp) else 4 if exp else 0, f"{len(exp)} entries")
    sk = p.get("skills") or []
    row("skills", (3 if len(sk) >= 20 else 1 if sk else 0) + (3 if p.get("pinned_skills") else 0), f"{len(sk)} skills")
    row("recommendations", min(3, int(p.get("recommendations") or 0)) * 8 // 3)
    act = int(p.get("posts_30d") or 0) * 5 + int(p.get("comments_30d") or 0)
    row("activity", 10 if act >= 20 else 5 if act else 0, f"{p.get('posts_30d', 0)} posts, {p.get('comments_30d', 0)} comments in 30 days")
    row("contact", (3 if p.get("custom_url") else 0) + (3 if p.get("contact") else 0))
    return sum(r[1] for r in rows), rows


# ---------- log ----------
def log_add(h, hook, pillar, file, date=None):
    p = h / "log.json"; log = load(p, [])
    text = pathlib.Path(file).read_text(encoding="utf-8") if file else ""
    rec = dict(id=(max([r["id"] for r in log]) + 1) if log else 1, date=date or datetime.date.today().isoformat(),
               hook=hook, pillar=pillar, chars=len(text.strip()), preview=text.strip()[:80], views=None, comments=None, reactions=None)
    log.append(rec); save(p, log)
    return rec


def log_result(h, id, **kw):
    p = h / "log.json"; log = load(p, [])
    for r in log:
        if r["id"] == id:
            r.update({k: v for k, v in kw.items() if v is not None}); save(p, log); return r
    raise SystemExit(f"no post with id {id}")


def log_stats(h):
    log = [r for r in load(h / "log.json", []) if r.get("views") is not None]
    out = {}
    for key in ("hook", "pillar"):
        groups = {}
        for r in log:
            groups.setdefault(r.get(key) or "?", []).append(r)
        out[key] = sorted(((k, len(v), sum(r["views"] for r in v) / len(v), sum(r.get("comments") or 0 for r in v) / len(v)) for k, v in groups.items()),
                          key=lambda x: -x[2])
    return out, len(log)


# ---------- network ----------
def net_add(h, name, company, why, days=7, today=None):
    p = h / "network.json"; net = load(p, [])
    today = today or datetime.date.today()
    rec = dict(id=(max([r["id"] for r in net]) + 1) if net else 1, name=name, company=company, why=why,
               added=today.isoformat(), last=None, touches=0, next=(today + datetime.timedelta(days=days)).isoformat(), note="")
    net.append(rec); save(p, net)
    return rec


def net_touch(h, id, days=14, note="", today=None):
    p = h / "network.json"; net = load(p, [])
    today = today or datetime.date.today()
    for r in net:
        if r["id"] == id:
            r.update(last=today.isoformat(), touches=r.get("touches", 0) + 1, next=(today + datetime.timedelta(days=days)).isoformat(), note=note or r.get("note", ""))
            save(p, net); return r
    raise SystemExit(f"no contact with id {id}")


def net_due(h, today=None):
    today = today or datetime.date.today()
    return sorted((r for r in load(h / "network.json", []) if r.get("next") and r["next"] <= today.isoformat()), key=lambda r: r["next"])


# ---------- cli ----------
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--home", help="state folder (default ~/.pentarch/linkedin)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").add_argument("file")
    sub.add_parser("profile").add_argument("file")
    lg = sub.add_parser("log").add_subparsers(dest="sub", required=True)
    a = lg.add_parser("add"); a.add_argument("--hook", required=True); a.add_argument("--pillar", required=True); a.add_argument("--file"); a.add_argument("--date")
    r = lg.add_parser("result"); r.add_argument("id", type=int); r.add_argument("--views", type=int); r.add_argument("--comments", type=int); r.add_argument("--reactions", type=int)
    lg.add_parser("stats")
    nt = sub.add_parser("network").add_subparsers(dest="sub", required=True)
    n = nt.add_parser("add"); n.add_argument("--name", required=True); n.add_argument("--company", default=""); n.add_argument("--why", default=""); n.add_argument("--days", type=int, default=7)
    t = nt.add_parser("touch"); t.add_argument("id", type=int); t.add_argument("--days", type=int, default=14); t.add_argument("--note", default="")
    nt.add_parser("due")
    a = ap.parse_args(argv)
    h = home(a.home)
    if a.cmd == "check":
        rows = check_text(pathlib.Path(a.file).read_text(encoding="utf-8"))
        for lvl, msg in rows:
            print(f"{lvl:4} {msg}")
        return 1 if any(l == "FAIL" for l, _ in rows) else 0
    if a.cmd == "profile":
        total, rows = score_profile(json.loads(pathlib.Path(a.file).read_text(encoding="utf-8")))
        for key, got, mx, note in rows:
            print(f"{got:2}/{mx:2} {key:17} {note}")
        print(f"{total}/100")
        print("fix first: " + ", ".join(f"{k} ({mx - got})" for k, got, mx, _ in sorted(rows, key=lambda r: r[1] - r[2])[:3] if got < mx))
        return 0
    if a.cmd == "log":
        if a.sub == "add":
            rec = log_add(h, a.hook, a.pillar, a.file, a.date); print(f"logged post {rec['id']} ({rec['hook']} / {rec['pillar']}, {rec['chars']} chars)")
        elif a.sub == "result":
            rec = log_result(h, a.id, views=a.views, comments=a.comments, reactions=a.reactions); print(f"post {rec['id']}: {rec['views']} views, {rec['comments']} comments")
        else:
            stats, n = log_stats(h)
            print(f"{n} posts with results")
            for key in ("hook", "pillar"):
                print(f"by {key}:")
                for k, cnt, views, com in stats[key]:
                    print(f"  {views:8.0f} views  {com:5.1f} comments  n={cnt}  {k}")
        return 0
    if a.cmd == "network":
        if a.sub == "add":
            rec = net_add(h, a.name, a.company, a.why, a.days); print(f"contact {rec['id']}: {rec['name']} ({rec['company']}), follow up {rec['next']}")
        elif a.sub == "touch":
            rec = net_touch(h, a.id, a.days, a.note); print(f"contact {rec['id']}: touch {rec['touches']}, next {rec['next']}")
        else:
            due = net_due(h)
            print(f"{len(due)} due") if due else print("nothing due")
            for r in due:
                print(f"  {r['id']:3} {r['next']} {r['name']} ({r['company']}) {r['why']} [{r.get('touches', 0)} touches]")
        return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
