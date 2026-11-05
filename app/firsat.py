"""Opportunity watch: open hackathons (Devpost) and remote software jobs (Remotive), only ones not seen before.

No packages, no model; public JSON endpoints. Seen ids are kept in <home>/firsat.json.
    python -I firsat.py          # new ones (and marks them seen)
    python -I firsat.py --hepsi  # show all, mark nothing
The morning brief runs this and suggests what is new and fits the owner.
Config "opportunities" (every key optional):
    devpost            true | false            hackathons on/off
    remotive_category  "software-dev"          Remotive category slug; "" turns jobs off
    locations          ["worldwide", ...]      a job/hackathon location must contain one (online hackathons always pass)
    keywords           []                      a job title or tag must contain one; empty means any
    exclude            ["senior", ...]         titles containing one are dropped
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import C, HOME, T  # noqa: E402

STATE = HOME / "firsat.json"
UA = {"User-Agent": "Mozilla/5.0 pentarch-opportunities"}
DEFAULT = {"devpost": True, "remotive_category": "software-dev",
           "locations": ["worldwide", "anywhere", "global", "europe"], "keywords": [],
           "exclude": ["senior", "sr.", "lead", "head", "principal", "staff", "director", "manager"]}
CFG = {**DEFAULT, **(C.get("opportunities") or {})}


def words(items):
    """Case-insensitive regex for any of the words, not matching inside longer words; None if the list is empty."""
    items = [w for w in items if w]
    return re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, items)) + r")(?!\w)", re.I) if items else None


LOCATIONS, KEYWORDS, EXCLUDE = words(CFG["locations"]), words(CFG["keywords"]), words(CFG["exclude"])


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
        return json.load(r)


def hackathons():
    out = []
    for page in (1, 2):
        for h in get(f"https://devpost.com/api/hackathons?status[]=open&status[]=upcoming&page={page}")["hackathons"]:
            loc = h.get("displayed_location", {}).get("location", "")
            if loc != "Online" and not (LOCATIONS and LOCATIONS.search(loc)):
                continue
            prize = re.sub(r"<[^>]+>", "", h.get("prize_amount") or "")
            themes = ", ".join(t["name"] for t in h.get("themes", []))
            out.append((f"devpost-{h['id']}", f"Hackathon: {h['title']} ({h.get('submission_period_dates')}, "
                        f"{h.get('time_left_to_submission')}, {T('ödül', 'prize')} {prize}, {themes}) {h['url']}"))
    return out


def jobs():
    out = []
    for j in get(f"https://remotive.com/api/remote-jobs?category={CFG['remotive_category']}&limit=200")["jobs"]:
        if LOCATIONS and not LOCATIONS.search(j.get("candidate_required_location", "")):
            continue
        title = j["title"]
        if EXCLUDE and EXCLUDE.search(title):
            continue
        if KEYWORDS and not KEYWORDS.search(title + " " + " ".join(j.get("tags") or [])):
            continue
        out.append((f"remotive-{j['id']}", f"{T('İlan', 'Job')}: {title}, {j['company_name']} "
                    f"({j['candidate_required_location']}, {j.get('job_type')}, {j['publication_date'][:10]}) {j['url']}"))
    return out


def main():
    if sys.argv[1:2] in (["-h"], ["--help"]):
        sys.exit(__doc__)
    show_all = "--hepsi" in sys.argv
    seen = set(json.loads(STATE.read_text(encoding="utf-8"))) if STATE.exists() else set()
    sources = ([hackathons] if CFG["devpost"] else []) + ([jobs] if CFG["remotive_category"] else [])
    found, errors = [], []
    for source in sources:
        try:
            found += source()
        except Exception as e:
            errors.append(f"{source.__name__}: {e!r}")
    new = [(k, line) for k, line in found if show_all or k not in seen]
    for _, line in new:
        print(line)
    for e in errors:
        print(T("HATA:", "ERROR:"), e)
    if not new:
        print(T("yeni fırsat yok", "no new opportunities"))
    if not show_all:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(sorted(seen | {k for k, _ in found})), encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
