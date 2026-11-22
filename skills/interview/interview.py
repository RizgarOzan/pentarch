# -*- coding: utf-8 -*-
"""Story bank for interview prep (Pentarch interview skill). Standard library only, no model, no network.

    python interview.py add --title T --tags a,b --situation S --action A --result R [--reflection X] [--file stories.json]
    python interview.py list
    python interview.py match "Tell me about a time you disagreed with a teammate"   best stories for a question
    python interview.py check [TITLE]     checks the stories: a number in the result, "I" not "we", short enough to say

A story is Situation, Action, Result and a Reflection (what you would do differently). The bank is one JSON file the
owner keeps; the words in it are the owner's own, this script never writes or changes a story's text.
"""
import argparse, json, pathlib, re, sys

THEMES = {  # question words -> the tag they usually mean; a story's tags are matched against these as well as the raw words
    "conflict": ("disagree", "conflict", "difficult", "pushback", "argue", "tension", "uyuşmazlık", "anlaşmazlık", "konflikt"),
    "leadership": ("lead", "led", "mentor", "organize", "initiative", "liderlik", "führung"),
    "failure": ("fail", "mistake", "wrong", "regret", "hata", "başarısız", "fehler"),
    "deadline": ("deadline", "pressure", "tight", "late", "prioritize", "priorit", "stress", "süre", "zaman", "termin"),
    "impact": ("proud", "achievement", "impact", "improve", "başarı", "gurur", "erfolg"),
    "teamwork": ("team", "collaborat", "together", "peer", "takım", "ekip", "zusammen"),
    "technical": ("debug", "design", "architecture", "performance", "bug", "technical", "teknik"),
    "learning": ("learn", "quickly", "unfamiliar", "self-taught", "öğren", "lernen"),
}
FILLER = {"a", "the", "of", "to", "me", "you", "your", "about", "time", "when", "tell", "is", "was", "and", "in", "it"}
SPEAK_WORDS = 220  # about 90 seconds spoken
WORD = re.compile(r"[\wçğıöşüÇĞİÖŞÜ'-]+")


def load(path):
    p = pathlib.Path(path)
    return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else []


def save(path, stories):
    p = pathlib.Path(path)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(stories, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def words(s):
    return {w.lower() for w in WORD.findall(s)}


def match(question, stories, top=3):
    """Stories ranked by overlap between the question and each story's tags (weight 3), then its text (weight 1)."""
    q = question.lower()
    qwords = words(q) - FILLER
    themes = {t for t, keys in THEMES.items() if any(k in q for k in keys)}
    scored = []
    for s in stories:
        tags = {t.strip().lower() for t in s.get("tags", [])}
        score = 3 * len(tags & (qwords | themes))
        score += len(words(" ".join(str(s.get(k, "")) for k in ("title", "situation", "action", "result"))) & qwords)
        if score:
            scored.append((score, s))
    return [s for _, s in sorted(scored, key=lambda x: -x[0])[:top]]


def check(s):
    """Problems with one story, as (level, text). Never changes it."""
    out = []
    n = len(WORD.findall(" ".join(str(s.get(k, "")) for k in ("situation", "action", "result"))))
    if not re.search(r"\d", s.get("result", "")):
        out.append(("WARN", "result has no number; a count, a time or a percentage is what the listener remembers (do not invent one)"))
    act = s.get("action", "")
    if re.search(r"\b(we|our|us|wir|biz)\b", act, re.I) and not re.search(r"\b(i|ich|ben)\b", act, re.I):
        out.append(("WARN", "the action says we/our only; the interviewer is asking what you did, say 'I'"))
    if n > SPEAK_WORDS:
        out.append(("WARN", f"{n} words is over 90 seconds spoken; cut the situation first"))
    if not s.get("reflection"):
        out.append(("WARN", "no reflection; add what you would do differently (it is the part that shows you learn)"))
    if len(words(s.get("action", ""))) * 2 < len(words(s.get("situation", ""))):
        out.append(("WARN", "the situation is much longer than the action; the action is the story"))
    return out


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--file", default="stories.json")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("add")
    for k in ("title", "situation", "action", "result"): p.add_argument("--" + k, required=True)
    p.add_argument("--tags", default=""); p.add_argument("--reflection", default="")
    sub.add_parser("list")
    p = sub.add_parser("match"); p.add_argument("question")
    p = sub.add_parser("check"); p.add_argument("title", nargs="?")
    a = ap.parse_args(argv)
    stories = load(a.file)
    if a.cmd == "add":
        s = dict(title=a.title.strip(), tags=[t.strip().lower() for t in a.tags.split(",") if t.strip()], situation=a.situation,
                 action=a.action, result=a.result, reflection=a.reflection)
        stories = [x for x in stories if x["title"].lower() != s["title"].lower()] + [s]
        save(a.file, stories)
        print(f"saved: {s['title']} ({len(stories)} in the bank)")
        return 0
    if a.cmd == "list":
        for s in stories:
            print(f"{s['title']}\t{','.join(s.get('tags', []))}")
        covered = {t for s in stories for t in s.get("tags", [])}
        gap = [t for t in THEMES if t not in covered]
        if gap:
            print("no story yet for: " + ", ".join(gap))
        return 0
    if a.cmd == "match":
        hits = match(a.question, stories)
        for s in hits:
            print(f"{s['title']}\n  S: {s['situation']}\n  A: {s['action']}\n  R: {s['result']}")
        if not hits:
            print("no story fits; ask the owner for a real example before writing an answer")
        return 0 if hits else 1
    bad = 0
    for s in stories:
        if a.title and s["title"].lower() != a.title.lower():
            continue
        for level, text in check(s):
            print(f"{level} {s['title']}: {text}")
            bad += 1
    print("ok" if not bad else f"{bad} note(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
