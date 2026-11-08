"""Career watch: entry-level openings on companies' Greenhouse, Lever and Ashby job boards, only ones not seen before.

No packages, no model; public JSON endpoints. Seen ids are kept in <home>/kariyer.json.
    python -I kariyer.py          # new ones (and marks them seen)
    python -I kariyer.py --hepsi  # show all, mark nothing
The morning brief runs this and suggests new openings that fit the owner.
Config "job_boards" (every key optional; with no companies the script does nothing):
    greenhouse  []                 board slugs, e.g. ["anthropic", "cloudflare"] (boards.greenhouse.io/<slug>)
    lever       []                 company slugs, e.g. ["spotify"] (jobs.lever.co/<slug>)
    lever_eu    []                 the same for EU-hosted boards (jobs.eu.lever.co/<slug>)
    ashby       []                 board names, e.g. ["openai"] (jobs.ashbyhq.com/<name>); the salary comes along
    titles      ["intern", ...]    a title must contain one; empty means any level
    fields      ["engineer", ...]  a title must also contain one; empty means any field
    exclude     ["senior", ...]    titles containing one are dropped
    locations   []                 a location must contain one ("remote", "berlin"...); empty means anywhere
A posting whose text says it won't sponsor a visa or needs a security clearance gets a warning at the end.
The Ashby and EU Lever endpoints and the idea of reading must-haves from the text come from jobleft (MIT,
github.com/Blueturboguy07/jobleft).
"""
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import C, HOME, T  # noqa: E402

STATE = HOME / "kariyer.json"
UA = {"User-Agent": "Mozilla/5.0 pentarch-careers"}
DEFAULT = {"greenhouse": [], "lever": [], "lever_eu": [], "ashby": [],
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


MUST = [(re.compile(r"(no|not|unable to|cannot|can't|won't|will not|without)( offer| provide)?( visa)? sponsor|"
                     r"sponsorship (is )?not (available|offered|provided)|must (already )?(be|have) (legally )?"
                     r"authori[sz]ed to work", re.I), T("vize sponsoru yok", "no visa sponsorship")),
        (re.compile(r"security clearance|clearance (is )?required|active (secret|ts/sci)", re.I),
         T("güvenlik izni ister", "needs security clearance"))]


def warn(text):
    """' ⚠ ...' for the must-haves the posting's text states, '' when none."""
    text = re.sub(r"<[^>]+>", " ", html.unescape(text or ""))
    hits = [label for rx, label in MUST if rx.search(text)]
    return f" ⚠ {', '.join(hits)}" if hits else ""


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
                        f"{j['absolute_url']}{warn(gh_text(company, j['id']))}"))
    return out


def gh_text(company, job_id):
    """The board list has no text; it is read only for postings that already fit (all of it is ~10x the bytes)."""
    return get(f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{job_id}").get("content")


def lever(company, host="api.lever.co"):
    out = []
    for j in get(f"https://{host}/v0/postings/{company}?mode=json"):
        cat = j.get("categories") or {}
        loc = ", ".join(cat.get("allLocations") or [cat.get("location") or ""])
        if fits(j["text"], loc + " " + (j.get("workplaceType") or "")):
            out.append((f"lv-{company}-{j['id']}", f"{company}: {j['text']} ({loc}, {cat.get('commitment', '')}) "
                        f"{j['hostedUrl']}{warn(lever_text(j))}"))
    return out


def lever_text(j):
    parts = [j.get("descriptionPlain"), j.get("additionalPlain")] + [x.get("content") for x in j.get("lists") or []]
    return " ".join(x or "" for x in parts)


def lever_eu(company):
    return lever(company, "api.eu.lever.co")


def ashby(board):
    out = []
    for j in get(f"https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true")["jobs"]:
        if j.get("isListed") is False:
            continue
        loc = ", ".join([j.get("location") or ""] + [x.get("location", "") for x in j.get("secondaryLocations") or []])
        if fits(j["title"], loc + (" remote" if j.get("isRemote") else "")):
            pay = (j.get("compensation") or {}).get("compensationTierSummary") or ""
            out.append((f"ab-{board}-{j['id']}", f"{board}: {j['title']} ({loc}{', ' + pay if pay else ''}, "
                        f"{(j.get('publishedAt') or '')[:10]}) {j['jobUrl']}{warn(j.get('descriptionPlain'))}"))
    return out


def main():
    if sys.argv[1:2] in (["-h"], ["--help"]):
        sys.exit(__doc__)
    show_all = "--hepsi" in sys.argv
    boards = [(f, c) for f in (greenhouse, lever, lever_eu, ashby) for c in CFG[f.__name__]]
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
