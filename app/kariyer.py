"""Career watch: entry-level openings on companies' Greenhouse and Lever job boards, only ones not seen before.

No packages, no model; public JSON endpoints. Seen ids are kept in <home>/kariyer.json.
    python -I kariyer.py          # new ones (and marks them seen)
    python -I kariyer.py --hepsi  # show all, mark nothing
The morning brief runs this and suggests new openings that fit the owner.
Config "job_boards" (every key optional; with no companies the script does nothing):
    greenhouse  []                 board slugs, e.g. ["anthropic", "cloudflare"] (boards.greenhouse.io/<slug>)
    lever       []                 company slugs, e.g. ["spotify"] (jobs.lever.co/<slug>)
    titles      ["intern", ...]    a title must contain one; empty means any level
    fields      ["engineer", ...]  a title must also contain one; empty means any field
    exclude     ["senior", ...]    titles containing one are dropped
    locations   []                 a location must contain one ("remote", "berlin"...); empty means anywhere
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import C, HOME, T  # noqa: E402

STATE = HOME / "kariyer.json"
UA = {"User-Agent": "Mozilla/5.0 pentarch-careers"}
DEFAULT = {"greenhouse": [], "lever": [],
           "titles": ["intern", "internship", "junior", "graduate", "new grad", "entry", "trainee"],
           "fields": ["engineer", "developer", "software"],
           "exclude": ["senior", "sr.", "lead", "head", "principal", "staff", "director", "manager"],
           "locations": []}
CFG = {**DEFAULT, **(C.get("job_boards") or {})}


def words(items):
    """Case-insensitive regex for any of the words, not matching inside longer words; None if the list is empty."""
    items = [w for w in items if w]
    return re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, items)) + r")(?!\w)", re.I) if items else None


TITLES, FIELDS, EXCLUDE, LOCATIONS = (words(CFG[k]) for k in ("titles", "fields", "exclude", "locations"))


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)


def fits(title, location):
    return ((not TITLES or TITLES.search(title)) and (not FIELDS or FIELDS.search(title))
            and not (EXCLUDE and EXCLUDE.search(title)) and (not LOCATIONS or LOCATIONS.search(location or "")))


def greenhouse(company):
    out = []
    for j in get(f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs")["jobs"]:
        loc = (j.get("location") or {}).get("name", "")
        if fits(j["title"], loc):
            out.append((f"gh-{company}-{j['id']}", f"{company}: {j['title']} ({loc}, {j.get('updated_at', '')[:10]}) "
                        f"{j['absolute_url']}"))
    return out


def lever(company):
    out = []
    for j in get(f"https://api.lever.co/v0/postings/{company}?mode=json"):
        cat = j.get("categories") or {}
        loc = ", ".join(cat.get("allLocations") or [cat.get("location") or ""])
        if fits(j["text"], loc + " " + (j.get("workplaceType") or "")):
            out.append((f"lv-{company}-{j['id']}", f"{company}: {j['text']} ({loc}, {cat.get('commitment', '')}) "
                        f"{j['hostedUrl']}"))
    return out


def main():
    if sys.argv[1:2] in (["-h"], ["--help"]):
        sys.exit(__doc__)
    show_all = "--hepsi" in sys.argv
    boards = [(greenhouse, c) for c in CFG["greenhouse"]] + [(lever, c) for c in CFG["lever"]]
    if not boards:
        print(T("job_boards ayarında şirket yok", "no companies in the job_boards setting"))
        return
    seen = set(json.loads(STATE.read_text(encoding="utf-8"))) if STATE.exists() else set()
    found, errors = [], []
    for source, c in boards:
        try:
            found += source(c)
        except Exception as e:
            errors.append(f"{source.__name__}/{c}: {e!r}")
    new = [(k, line) for k, line in found if show_all or k not in seen]
    for _, line in new:
        print(line)
    for e in errors:
        print(T("HATA:", "ERROR:"), e)
    if not new:
        print(T("yeni ilan yok", "no new openings"))
    if not show_all:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(sorted(seen | {k for k, _ in found})), encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
