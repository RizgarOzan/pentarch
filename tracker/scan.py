# -*- coding: utf-8 -*-
"""Job scan without a model: reads the public job boards named in profile.json, scores every posting against the
profile, and writes data/scan.json for build.py. Standard library only.

    python tracker/scan.py --config tracker/config.json            # scan, score, write scan.json + scan-state.json
    python tracker/scan.py --config tracker/config.json --dry-run  # print the result, write nothing

profile.json keys it reads (all optional, see profile.example.json):
    boards        {"greenhouse": [slugs], "lever": [slugs], "ashby": [slugs]}
    seniority     words a title must contain ("intern", "junior", "entry level"; synonyms are built in)
    exclude       words that rule a title out ("senior", "lead", ...)
    target_roles  role words that raise the score when they appear in the title
    locations     a posting's location must contain one; "remote" also accepts remote flags
    skills        counted in the description; the ones missing from the profile are listed as "missing"
    signals       {"strong": [phrases], "weak": [phrases], "deal_breakers": [phrases]} matched in the description
    max_years     "N+ years" above this in the description counts as a deal breaker (default 2)
    quality.min_score  1-5; postings under it go to "dropped"

Score, 1-5: role fit, skills found, strong and weak signals, freshness. Deal breakers and location misses drop a
posting before scoring. applications.json feeds back: a company you already track is reported under "changed",
and a company whose closed record says it rejected you loses a point.
"""
import argparse, datetime, html, json, pathlib, re, sys, urllib.request

HERE = pathlib.Path(__file__).parent
UA = {"User-Agent": "Mozilla/5.0 pentarch-tracker"}
SYN = {"intern": ["intern", "internship", "stajyer", "working student"],
       "junior": ["junior", "jr", "jr."],
       "entry level": ["entry level", "entry-level", "graduate", "new grad", "new graduate", "early career", "associate", "trainee", "apprentice"]}
EXCLUDE = ["senior", "sr", "sr.", "lead", "head", "principal", "staff", "director", "manager", "vp", "chief"]
STOP = {"developer", "engineer", "programmer", "and", "or", "the", "a", "an", "of",  # too common to tell roles apart
        "junior", "senior", "intern", "mid", "entry", "level", "new", "grad", "graduate"}  # seniority, handled separately
YEARS = re.compile(r"(\d+)\s*(?:\+|-|–|to)?\s*(?:\d+)?\s*\+?\s*(?:years|yrs|yıl)['’]?\s*(?:of\s+)?(?:[\w-]+[\s,]+){0,3}?"
                   r"(?:experience|exp\b|deneyim|background|working|track record|in\b|with\b)", re.I)  # "founded 10 years ago" is not a requirement
REMOTE = re.compile(r"\bremote\b|anywhere|worldwide|distributed", re.I)


def words(items):
    items = [w for w in items if w]
    return re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, items)) + r")(?!\w)", re.I) if items else None


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)


def plain(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(s or ""))).strip()


def day(s):
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


# ---------- sources: each yields dicts with id, company, title, location, remote, posted, link, text ----------
def greenhouse(slug):
    for j in get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")["jobs"]:
        yield dict(id=f"gh-{slug}-{j['id']}", company=j.get("company_name") or slug, title=j["title"].strip(),
                   location=(j.get("location") or {}).get("name", ""), remote=False,
                   posted=j.get("first_published") or j.get("updated_at"), link=j["absolute_url"], text=plain(j.get("content")))


def lever(slug):
    for j in get(f"https://api.lever.co/v0/postings/{slug}?mode=json"):
        cat = j.get("categories") or {}
        loc = ", ".join(cat.get("allLocations") or [cat.get("location") or ""])
        posted = datetime.datetime.fromtimestamp(j["createdAt"] / 1000, datetime.timezone.utc).date().isoformat() if j.get("createdAt") else ""
        yield dict(id=f"lv-{slug}-{j['id']}", company=slug, title=j["text"].strip(), location=loc,
                   remote=(j.get("workplaceType") or "").lower() == "remote", posted=posted, link=j["hostedUrl"],
                   text=plain(j.get("descriptionPlain") or j.get("description")))


def ashby(slug):
    for j in get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")["jobs"]:
        if j.get("isListed") is False:
            continue
        loc = ", ".join([j.get("location") or ""] + [x.get("location", "") for x in j.get("secondaryLocations") or []])
        yield dict(id=f"ab-{slug}-{j['id']}", company=slug, title=j["title"].strip(), location=loc, remote=bool(j.get("isRemote")),
                   posted=j.get("publishedAt"), link=j.get("jobUrl"), text=plain(j.get("descriptionPlain") or j.get("descriptionHtml")))


SOURCES = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}


# ---------- scoring ----------
class Scorer:
    def __init__(self, profile, applications=(), today=None):
        p = profile
        self.today = today or datetime.date.today()
        sen = [s for k in (p.get("seniority") or []) for s in SYN.get(k.lower(), [k])]
        self.seniority, self.exclude = words(sen), words(EXCLUDE if p.get("exclude") is None else p["exclude"])
        # a role counts in full when every one of its words is in the title; its last word alone ("designer") is a weak hit
        parts = {r: [w for w in re.findall(r"[\w#+.]+", r) if w.lower() not in STOP and len(w) > 1] for r in p.get("target_roles") or []}
        self.roles = [(r, [words([w]) for w in ws]) for r, ws in parts.items() if ws]
        self.role_nouns = words(list({ws[-1].lower() for ws in parts.values() if ws}))
        locs = [l for l in p.get("locations") or [] if not l.lower().startswith("relocation")]
        self.locations, self.want_remote = words(locs), any(REMOTE.search(l) for l in locs)
        self.skills = {s: words([s]) for s in p.get("skills") or []}
        sig = p.get("signals") or {}
        self.strong, self.weak, self.breakers = (words(sig.get(k) or []) for k in ("strong", "weak", "deal_breakers"))
        try:
            self.max_years = int(p.get("max_years") or 2)
        except (TypeError, ValueError):
            raise SystemExit(f"profile max_years must be a number, got {p.get('max_years')!r}")
        self.min_score = int((p.get("quality") or {}).get("min_score", 3))
        self.open = {a.get("company", "").lower(): a for a in applications if a.get("stage") != "closed" and a.get("company")}
        self.rejected = {a["company"].lower() for a in applications if a.get("company") and a.get("stage") == "closed"
                         and re.search(r"\brejected?\b|\bdeclined?\b|\bred\b|olumsuz|turned down", (a.get("status") or "") + (a.get("note") or ""), re.I)}

    def judge(self, j):
        """Returns (score 1-5 or 0 when dropped, reason, extra fields)."""
        t, loc, text = j["title"], j.get("location") or "", j.get("text") or ""
        if self.exclude and self.exclude.search(t):
            return 0, "excluded word: " + self.exclude.search(t).group(0).lower(), {}
        if self.seniority and not self.seniority.search(t):
            return 0, "title lacks a seniority word", {}
        if self.locations and not (self.locations.search(loc) or (self.want_remote and (j.get("remote") or REMOTE.search(loc)))):
            return 0, f"location: {loc or '?'}", {}
        if self.breakers and self.breakers.search(text):
            return 0, "deal breaker: " + self.breakers.search(text).group(0), {}
        years = [int(m.group(1)) for m in YEARS.finditer(text)]
        if years and max(years) > self.max_years and min(years) > self.max_years:
            return 0, f"asks for {min(years)}+ years", {}
        pts, why = 0, []
        full = [r for r, ws in self.roles if all(w.search(t) for w in ws)]
        if full:
            pts += 2; why.append("role: " + ", ".join(full))
        elif self.role_nouns and self.role_nouns.search(t):
            pts += 1; why.append("role word: " + self.role_nouns.search(t).group(0).lower())
        elif self.role_nouns:
            return 0, "title: no target role", {}
        have = [s for s, rx in self.skills.items() if rx.search(text) or rx.search(t)]
        if have:
            pts += min(2, len(have)); why.append("skills: " + ", ".join(have))
        if self.strong and self.strong.search(text):
            pts += 1; why.append("+" + self.strong.search(text).group(0))
        if self.weak and self.weak.search(text):
            pts -= 1; why.append("-" + self.weak.search(text).group(0))
        age = (self.today - day(j.get("posted"))).days if day(j.get("posted")) else None
        if age is not None and age > 90:
            pts -= 1; why.append(f"posted {age} days ago")
        elif age is not None and age <= 14:
            pts += 1; why.append("fresh")
        if j["company"].lower() in self.rejected:
            pts -= 1; why.append("rejected you before")
        score = max(1, min(5, 1 + pts))
        return score, "; ".join(why) or "entry-level title, nothing else matched", {"years": years[:3], "age": age}


def run(profile, config, today=None, fetch=None):
    """Scans, scores, diffs against scan-state.json. Returns (scan dict, state dict, errors)."""
    data = pathlib.Path(config["data_dir"])
    today = today or datetime.date.today()
    apps = json.loads((data / "applications.json").read_text(encoding="utf-8")) if (data / "applications.json").exists() else []
    old = json.loads((data / "scan-state.json").read_text(encoding="utf-8")) if (data / "scan-state.json").exists() else {}
    sc, fetch = Scorer(profile, apps, today), fetch or (lambda src, slug: list(SOURCES[src](slug)))
    seen, new, changed, dropped, errors, sources = {}, [], [], [], [], []
    for src, slugs in (profile.get("boards") or {}).items():
        if src.startswith("_"):  # comment key from profile.example.json
            continue
        if src not in SOURCES:
            errors.append(f"unknown board type {src}"); continue
        for slug in slugs:
            try:
                jobs = fetch(src, slug)
            except Exception as e:
                errors.append(f"{src}/{slug}: {e!r}"); continue
            sources.append(f"{src}/{slug}")
            for j in jobs:
                score, why, extra = sc.judge(j)
                rec = dict(company=j["company"], role=j["title"], link=j["link"], location=j.get("location", ""), score=score, reason=why, posted=str(j.get("posted") or "")[:10])
                seen[j["id"]] = dict(company=j["company"], role=j["title"], score=score, src=f"{src}/{slug}",
                                     first=old.get(j["id"], {}).get("first", today.isoformat()), last=today.isoformat())
                if score == 0:
                    if j["id"] not in old: dropped.append(dict(company=j["company"], role=j["title"], reason=why))
                    continue
                if j["company"].lower() in sc.open:
                    changed.append(dict(company=j["company"], what=f"already tracked ({sc.open[j['company'].lower()].get('stage')}): {j['title']} {score}/5"))
                elif j["id"] not in old:
                    (new if score >= sc.min_score else dropped).append(rec if score >= sc.min_score else dict(company=j["company"], role=j["title"], reason=f"{score}/5 under min_score: {why}"))
                elif old[j["id"]].get("score", 0) < sc.min_score <= score:
                    changed.append(dict(company=j["company"], what=f"now {score}/5 (was {old[j['id']].get('score')}): {j['title']}"))
    new.sort(key=lambda r: (-r["score"], r["posted"]))
    # a posting counts as gone only when its board was actually read this run (a fetch error must not close everything)
    closed = [dict(company=v["company"], reason=f"gone from the board: {v['role']}") for k, v in old.items()
              if k not in seen and v.get("score", 0) >= sc.min_score and v.get("src") in sources]
    top = ", ".join(f"{r['company']} ({r['score']}/5)" for r in new[:3])
    summary = (f"{len(seen)} postings on {len(sources)} boards; {len(new)} new at {sc.min_score}/5 or better" + (f", best: {top}" if top else "")
               + f"; {len(closed)} gone; {len(dropped)} dropped." + (f" Errors: {len(errors)}." if errors else ""))
    scan = dict(date=today.isoformat(), summary=summary, new=new, changed=changed, closed=closed, dropped=dropped, sources=sources, errors=errors)
    keep = {k: v for k, v in old.items() if day(v.get("last")) and (today - day(v["last"])).days < 60}
    return scan, {**keep, **seen}, errors


def main(argv=None):
    sys.path.insert(0, str(HERE))
    import build
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config"); ap.add_argument("--data"); ap.add_argument("--profile"); ap.add_argument("--today")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    cfg = build.load_config(a.config, **{k: v for k, v in dict(data_dir=a.data).items() if v})
    prof = pathlib.Path(a.profile) if a.profile else pathlib.Path(a.config).parent / "profile.json" if a.config else HERE / "profile.json"
    if not prof.exists():
        sys.exit(f"no profile at {prof}; copy profile.example.json there and add your boards")
    profile = json.loads(prof.read_text(encoding="utf-8"))
    if a.today and not day(a.today):
        sys.exit(f"--today must be YYYY-MM-DD, got {a.today!r}")
    scan, state, errors = run(profile, cfg, day(a.today))
    for e in errors:
        print("ERROR", e)
    print(scan["summary"])
    for r in scan["new"]:
        print(f"  {r['score']}/5 {r['company']}: {r['role']} ({r['location']}) {r['link']}\n      {r['reason']}")
    if a.dry_run:
        return scan, errors
    data = pathlib.Path(cfg["data_dir"]); data.mkdir(parents=True, exist_ok=True)
    (data / "scan.json").write_text(json.dumps(scan, ensure_ascii=False, indent=1), encoding="utf-8")
    (data / "scan-state.json").write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")
    return scan, errors


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(1 if main()[1] else 0)
