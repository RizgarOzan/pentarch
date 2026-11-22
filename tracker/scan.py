# -*- coding: utf-8 -*-
"""Job scan without a model: reads the public job boards named in profile.json, scores every posting against the
profile, and writes data/scan.json for build.py. Standard library only.

    python tracker/scan.py --config tracker/config.json            # scan, score, write scan.json + scan-state.json
    python tracker/scan.py --config tracker/config.json --dry-run  # print the result, write nothing

profile.json keys it reads (all optional, see profile.example.json):
    boards        {"greenhouse": [slugs], "lever": [...], "ashby": [...], "workable": [...], "recruitee": [...],
                   "smartrecruiters": [...], "personio": [...]} per company, plus aggregators that need no company list:
                   "remotive": [category, e.g. "software-dev"], "arbeitnow": [tag or "all"], "remoteok": [tag, e.g. "python"]
    seniority     words a title must contain ("intern", "junior", "entry level"; synonyms are built in)
    exclude       words that rule a title out ("senior", "lead", ...)
    target_roles  role words that raise the score when they appear in the title
    locations     a posting's location must contain one; "remote" also accepts remote flags. A location that names no
                  place ("Full-time", empty) is looked up in the title and the description instead, and kept if not found
    skills        counted in the description; the ones missing from the profile are listed as "missing"
    signals       {"strong": [phrases], "weak": [phrases], "deal_breakers": [phrases]} matched in the description
    max_years     "N+ years" above this in the description counts as a deal breaker (default 2)
    max_age_days  postings older than this are dropped (default 60; 0 keeps every age)
    applicant.education  when it names no computer science / software degree, a posting that requires one loses a point
    quality.min_score  1-5; postings under it go to "dropped"

Score, 1-5: role fit, skills found, strong and weak signals, freshness. Deal breakers and location misses drop a
posting before scoring. applications.json feeds back: a company you already track is reported under "changed",
and a company whose closed record says it rejected you loses a point.
"""
import argparse, datetime, html, json, pathlib, re, sys, urllib.error, urllib.request
import xml.etree.ElementTree as ET

HERE = pathlib.Path(__file__).parent
UA = {"User-Agent": "Mozilla/5.0 pentarch-tracker"}
SYN = {"intern": ["intern", "internship", "stajyer", "stajyeri", "stajyerler", "staj", "stajı", "stajyer adayı", "working student", "werkstudent", "werkstudentin", "praktikant", "praktikantin", "praktikum",
                  "werkstudierende", "werkstudierender", "studentische hilfskraft", "student assistant",
                  "becario", "becaria", "prácticas", "practicas", "pasante"],
       "junior": ["junior", "jr", "jr."],
       "entry level": ["entry level", "entry-level", "graduate", "new grad", "new graduate", "early career", "associate", "trainee", "apprentice",
                       "berufseinsteiger", "yeni mezun", "uzman yardımcısı", "management trainee", "recién graduado",
                       "recien graduado", "recién titulado"]}
EXCLUDE = ["senior", "sr", "sr.", "lead", "head", "principal", "staff", "director", "manager", "vp", "chief",
           "teamleiter", "teamleitung", "leitung", "abteilungsleiter", "bereichsleiter"]
DEV = {"developer", "engineer", "entwickler", "programmer", "programmierer", "geliştirici", "yazılımcı", "desarrollador"}
STOP = {"developer", "engineer", "programmer", "and", "or", "the", "a", "an", "of",  # too common to tell roles apart
        "junior", "senior", "intern", "mid", "entry", "level", "new", "grad", "graduate"}  # seniority, handled separately
YEARS = re.compile(r"(\d+|\b(?:one|two|three|four|five|six|seven|eight|nine|ten)\b)\s*(?:\+|-|–|to)?\s*(?:\d+)?\s*\+?\s*(?:years|yrs|yıl|jahren?|años)['’]?\s*(?:of\s+)?(?:[\w-]+[\s,]+){0,3}?"
                   r"(?:experience|exp\b|deneyim|(?:berufs)?erfahrung|experiencia|background|working|track record|in\b|with\b)", re.I)  # "founded 10 years ago" is not a requirement
NUM = {w: i for i, w in enumerate("one two three four five six seven eight nine ten".split(), 1)}
# "unable to offer visa sponsorship", "no security clearance required": the phrase is there, the meaning is the opposite
NEG_BEFORE = re.compile(r"\b(?:no|not|unable to|cannot|can't|won't|will not|without|don't|do not|does not)\b[^.;:!?\n]{0,30}$", re.I)
NEG_AFTER = re.compile(r"^\s*(?:is|are)?\s*(?:not\b|unavailable)", re.I)


def said(rx, text):
    """The first match of rx that the text doesn't negate, or None."""
    for m in rx.finditer(text) if rx else ():
        if not (NEG_BEFORE.search(text[max(0, m.start() - 40):m.start()]) or NEG_AFTER.search(text[m.end():m.end() + 20])):
            return m
    return None


AGE = re.compile(r"\b(?:seit|since|vor)\s+(?:(?:über|mehr als|more than|over)\s+)?$", re.I)  # "seit 15 Jahren in der Branche" is the company's age
REMOTE = re.compile(r"\bremote\b|\bremoto\b|teletrabajo|anywhere|worldwide|distributed|home[- ]?office|mobiles? arbeiten", re.I)
# "Remote - US only", "Remote (United States)", "Remote - Americas": remote, but not for someone outside that place
_LIMIT = r"US|USA|U\.S\.?|United States|Canada|UK|United Kingdom|India|Germany|Deutschland|DACH|Americas|North America|LATAM"
ONLY = re.compile(rf"\b({_LIMIT})[\s-]*(?:residents\s+|based\s+)?only\b|\bonly\s+(?:in\s+)?(?:the\s+)?({_LIMIT})\b|"
                  rf"\bremote\s*[(:,–—-]\s*({_LIMIT})\b(?:[\s-]*only\b)?", re.I)
REGIONS = {"americas": "us usa united states canada mexico méxico brazil brasil argentina chile colombia peru",
           "north america": "us usa united states canada mexico méxico",
           "latam": "mexico méxico brazil brasil argentina chile colombia peru uruguay",
           "dach": "germany deutschland austria österreich switzerland schweiz"}
# a place the user names also matches the other names boards use for it ("UK" finds "United Kingdom" and "England")
PLACES = [{"uk", "united kingdom", "great britain", "england", "scotland", "wales", "northern ireland"},
          {"us", "usa", "u.s.", "united states", "united states of america"},
          {"germany", "deutschland"}, {"turkey", "türkiye", "turkiye"}, {"netherlands", "the netherlands", "holland"},
          {"spain", "españa", "espana"}]
# board location fields that hold a job type instead of a place (Peak's Lever board says "Full-time")
NO_PLACE = re.compile(r"full[- ]?time|part[- ]?time|contract(?:or)?|permanent|temporary|internship|intern|freelance|"
                      r"vollzeit|teilzeit|festanstellung|unbefristet|befristet|"
                      r"hybrid|on[- ]?site|in[- ]?office|n/?a|tbd|various|multiple locations?|headquarters?|hq|[\s,;/|()-]", re.I)
CS_FIELD = r"(?:computer science|computer engineering|software engineering|informatik|cs)"
CS_DEGREE = re.compile(r"\b(?:degree|bachelor'?s?|master'?s?|ph\.?d|b\.?sc?|m\.?sc?|b\.?eng|m\.?eng|ba|bs|ms|studying|pursuing|"
                       r"major(?:ing)?|student)\b[^.;]{0,40}?\b" + CS_FIELD + r"\b|\b" + CS_FIELD + r"\s+(?:degree|major|student|graduate)\b", re.I)
CS_SOFT = re.compile(r"equivalent|related|similar|comparable|or (?:relevant |practical )?experience", re.I)
CS_OPTIONAL = re.compile(r"prefer|nice to have|bonus|\bplus\b|ideally|desirable|advantage", re.I)
CS_MINE = re.compile(r"computer science|computer engineering|software engineering|bilgisayar mühendisliği|bilgisayar bilimleri|"
                     r"yazılım mühendisliği|\binformatik\b|\bcs\b|\bceng\b", re.I)  # "Computer Education", MIS, "bilişim" are not CS degrees


# other names a posting uses for a skill in profile.json (same list as skills/cv/cv.py)
SAME = [("javascript", "js"), ("typescript", "ts"), ("postgresql", "postgres"), ("kubernetes", "k8s"),
        ("node.js", "nodejs", "node"), ("golang", "go"), ("c#", "csharp"), ("react", "react.js", "reactjs"),
        ("vue", "vue.js", "vuejs"), ("aws", "amazon web services"), ("gcp", "google cloud"), ("ml", "machine learning")]
ALIAS = {w: g for g in SAME for w in g}

# German asked in a posting, on the CEFR scale (6 = native); a "von Vorteil" line asks for nothing
CEFR = {"a1": 1, "a2": 2, "b1": 3, "b2": 4, "c1": 5, "c2": 6}
LEVEL = {6: "native", 5: "C1", 4: "B2", 3: "B1", 2: "A2", 1: "A1", 0: "none"}
GERMAN = re.compile(r"\b(?:deutsch(?!land)\w*|german)\b|almanca|alemán", re.I)
GERMAN_ASK = [(6, r"muttersprach\w*|native|mother tongue|\bc2\b"),
              (5, r"flie(?:ß|ss)end\w*|verhandlungssicher\w*|fluent|sehr gute?\w*|excellent|\bc1\b"),
              (4, r"\bgute?[nrs]?\b|\bgood\b|\bb2\b"), (3, r"\bb1\b")]
OPTIONAL = re.compile(r"von vorteil|wünschenswert|nice to have|\bplus\b|bonus|ideally|preferred|optional", re.I)


def german_asked(text):
    best = 0
    for m in GERMAN.finditer(text):
        near = text[max(0, m.start() - 30):m.end() + 30]
        if not OPTIONAL.search(near):
            best = max([best] + [lvl for lvl, rx in GERMAN_ASK if re.search(rx, near, re.I)])
    return best


def german_have(langs):
    """The profile's German level, 0 when German is not listed."""
    for entry in langs:
        if GERMAN.search(entry):
            if m := re.search(r"\b([abc][12])\b", entry, re.I):
                return CEFR[m.group(1).lower()]
            if re.search(r"native|mutter|ana ?dil", entry, re.I):
                return 6
            return 5 if re.search(r"fluent|flie|akıcı|ileri", entry, re.I) else 3
    return 0


def skill_rx(s):
    """A skill and its other names. A name of one or two letters (Go, R, C#, JS) counts only when written as a name
    and not as the start of a hyphen word, so "let's go" and "go-live" are not Go."""
    names = [s, *ALIAS.get(s.lower(), ())]
    long_ = [n for n in names if len(n) > 2]
    short = {v for n in names if len(n) <= 2 for v in (n[:1].upper() + n[1:], n.upper())}
    parts = [r"(?i:(?<!\w)(?:" + "|".join(map(re.escape, long_)) + r")(?!\w))"] if long_ else []
    if short:
        parts.append(r"(?<![\w'’])(?<!let's )(?<!Let's )(?:" + "|".join(map(re.escape, short)) + r")(?![\w#+]|-\w)")
    return re.compile("|".join(parts))


def words(items):
    items = [w for w in items if w]
    return re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, items)) + r")(?!\w)", re.I) if items else None


def stem(items):
    """Like words, but a word of 5+ letters may open a German compound: "software" finds "Softwareentwicklung".
    A long "-er" word loses the ending, so "designer" also finds "Product Design Graduate Scheme"."""
    items = [w[:-2] if len(w) >= 8 and w.lower().endswith("er") else w for w in items if w]
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(w) + ("" if len(w) >= 5 else r"(?!\w)") for w in items) + ")", re.I) if items else None


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)


def plain(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(s or ""))).strip()


def same(company, title):
    """One key for one job: "Junior Dev (m/w/d)" at "ACME GmbH" on two boards or in two cities is the same posting."""
    t = re.sub(r"(?<=\w)[:*_/]-?in(?:nen)?\b", "", title)  # "Entwickler:in", "Entwickler*in" = "Entwickler"
    t = re.sub(r"\([^)]*\)|\b[mwfdx]/[mwfdx](?:/[mwfdx])?\b|\s[-–|]\s.*$", " ", t.lower())
    c = re.sub(r"\b(gmbh|ag|inc|ltd|llc|se|bv|plc|corp|co)\b\.?", " ", company.lower())
    return re.sub(r"\W+", " ", c).strip() + "|" + re.sub(r"\W+", " ", t).strip()


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


def workable(slug):
    for j in get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true").get("jobs") or []:
        loc = ", ".join(x for x in (j.get("city"), j.get("country")) if x)
        yield dict(id=f"wk-{slug}-{j['shortcode']}", company=slug, title=j["title"].strip(), location=loc,
                   remote=str(j.get("telecommuting")).lower() == "true", posted=j.get("published_on"), link=j.get("url"),
                   text=plain(j.get("description")))


def recruitee(slug):
    for j in get(f"https://{slug}.recruitee.com/api/offers/").get("offers") or []:
        yield dict(id=f"rc-{slug}-{j['id']}", company=j.get("company_name") or slug, title=j["title"].strip(),
                   location=j.get("location") or "", remote=bool(j.get("remote")), posted=j.get("published_at"),
                   link=j.get("careers_url"), text=plain((j.get("description") or "") + " " + (j.get("requirements") or "")))


def smartrecruiters(slug):
    """The list has no description; it is fetched only for postings whose title passes (see Scorer.judge)."""
    base = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
    for offset in range(0, 500, 100):
        page = get(f"{base}?limit=100&offset={offset}")
        for j in page.get("content") or []:
            loc = j.get("location") or {}
            yield dict(id=f"sr-{slug}-{j['id']}", company=(j.get("company") or {}).get("name") or slug, title=j["name"].strip(),
                       location=loc.get("fullLocation") or "", remote=bool(loc.get("remote")), posted=j.get("releasedDate"),
                       link=f"https://jobs.smartrecruiters.com/{slug}/{j['id']}",
                       text=lambda u=f"{base}/{j['id']}": plain(" ".join(s.get("text") or "" for s in (
                           (get(u).get("jobAd") or {}).get("sections") or {}).values() if isinstance(s, dict))))
        if offset + 100 >= int(page.get("totalFound") or 0):
            break


def personio(slug):
    """Personio boards (common in Germany) publish XML; the board lives on .de or .com. No ?language: asking for en
    came back with empty descriptions for 290 of 328 postings on a German board."""
    root = None
    for tld in ("de", "com"):
        try:
            with urllib.request.urlopen(urllib.request.Request(f"https://{slug}.jobs.personio.{tld}/xml", headers=UA), timeout=60) as r:
                data = r.read(8_000_000)
        except urllib.error.HTTPError:
            continue
        # the real feed has no DOCTYPE; an unknown slug gets an HTML 404 page, and entity tricks need one too
        if b"<!doctype" not in data.lower():  # anywhere: a long comment could push it past any prefix we check
            root = ET.fromstring(data)
            break
    if root is None:
        raise ValueError(f"no Personio board named {slug!r}")
    for p in root.iter("position"):
        f = lambda k: (p.findtext(k) or "").strip()
        offices = [f("office")] + [o.text or "" for o in p.iter("additionalOffice")]
        text = " ".join(f"{d.findtext('name') or ''}: {d.findtext('value') or ''}" for d in p.iter("jobDescription"))
        yield dict(id=f"ps-{slug}-{f('id')}", company=f("subcompany") or slug, title=f("name"), location=", ".join(o for o in offices if o),
                   remote=bool(REMOTE.search(" ".join(offices))), posted=f("createdAt"),
                   link=f"https://{slug}.jobs.personio.{tld}/job/{f('id')}", text=plain(text))


# ---------- aggregators: no company slug needed; the "slug" is a category or tag ("" or "all" = everything) ----------
def remotive(cat):
    q = "" if cat in ("", "all") else f"?category={cat}"
    for j in get(f"https://remotive.com/api/remote-jobs{q}").get("jobs") or []:
        yield dict(id=f"rm-{j['id']}", company=j.get("company_name") or "?", title=j["title"].strip(),
                   location=j.get("candidate_required_location") or "", remote=True, posted=j.get("publication_date"),
                   link=j.get("url"), text=plain(j.get("description")))


def arbeitnow(tag):
    for p in (1, 2, 3):
        for j in get(f"https://www.arbeitnow.com/api/job-board-api?page={p}").get("data") or []:
            # tags are broad ("Engineering"), so a skill like "python" is looked for in the title and text too
            if tag not in ("", "all") and tag.lower() not in " ".join([*(j.get("tags") or []), j.get("title") or "", j.get("description") or ""]).lower():
                continue
            posted = datetime.datetime.fromtimestamp(int(j["created_at"]), datetime.timezone.utc).date().isoformat() if j.get("created_at") else ""
            yield dict(id=f"an-{j['slug']}", company=j.get("company_name") or "?", title=j["title"].strip(),
                       location=j.get("location") or "", remote=bool(j.get("remote")), posted=posted, link=j.get("url"),
                       text=plain(j.get("description")))


def remoteok(tag):
    q = "" if tag in ("", "all") else f"?tag={tag}"
    for j in get(f"https://remoteok.com/api{q}"):
        if not isinstance(j, dict) or not j.get("id"):  # the first row is the API's legal notice
            continue
        yield dict(id=f"ro-{j['id']}", company=j.get("company") or "?", title=(j.get("position") or "").strip(),
                   location=j.get("location") or "", remote=True, posted=j.get("date"), link=j.get("url"),
                   text=plain(j.get("description")))


SOURCES = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby, "workable": workable, "recruitee": recruitee,
           "smartrecruiters": smartrecruiters, "personio": personio, "remotive": remotive, "arbeitnow": arbeitnow, "remoteok": remoteok}


# ---------- scoring ----------
class Scorer:
    def __init__(self, profile, applications=(), today=None):
        p = profile
        self.today = today or datetime.date.today()
        sen = [s for k in (p.get("seniority") or []) for s in SYN.get(k.lower(), [k])]
        self.seniority, self.exclude = words(sen), words(EXCLUDE if p.get("exclude") is None else p["exclude"])
        # a role counts in full when every one of its words is in the title; its last word alone ("designer") is a weak hit
        stop = STOP | {w for v in SYN.values() for s in v for w in s.split()}  # "Werkstudent" is a level, not a role word
        parts = {r: [w for w in re.findall(r"[\w#+.]+", r) if w.lower() not in stop and len(w) > 1] for r in p.get("target_roles") or []}
        self.roles = [(r, [stem([w]) for w in ws]) for r, ws in parts.items() if ws]
        # the head noun is last in English ("data analyst") but first in Spanish ("analista de datos")
        nouns = {(ws[0] if {"de", "del"} & {w.lower() for w in ws} else ws[-1]).lower() for ws in parts.values() if ws}
        # "software engineer" left only "software"; "Junior Backend Developer" is that job too, and so is "Softwareentwickler"
        if "software" in nouns or re.search(r"develop|entwickl|engineer|programm", " ".join(parts), re.I):
            nouns |= DEV
        self.role_nouns = stem(list(nouns))
        locs = [l for l in p.get("locations") or [] if not l.lower().startswith("relocation")]
        locs += [l.split(",")[0].strip() for l in locs if "," in l]  # "Berlin, Germany" is also a "Berlin" posting
        locs += [a for l in locs for g in PLACES if l.lower().strip() in g for a in g]
        self.locations, self.want_remote = words(locs), any(REMOTE.search(l) for l in locs)
        # "Berlin, Germany" also lives in Germany, so "Remote (Germany)" is open to it
        # setup keeps only the city of "Austin, USA"; the country still decides whether "Remote - US" is open to you
        home = [(p.get("applicant") or {}).get("city") or ""]
        self.countries = words([a for l in locs + home for part in l.split(",") for g in PLACES if part.lower().strip() in g for a in g])
        self.skills = {s: skill_rx(s) for s in p.get("skills") or []}
        langs = (p.get("applicant") or {}).get("languages")
        langs = langs.split(",") if isinstance(langs, str) else langs
        self.german = german_have(langs) if langs else None  # no languages listed: unknown, not judged
        sig = p.get("signals") or {}
        self.strong, self.weak, self.breakers = (words(sig.get(k) or []) for k in ("strong", "weak", "deal_breakers"))
        try:
            self.max_years = int(p.get("max_years") or 2)
        except (TypeError, ValueError):
            raise SystemExit(f"profile max_years must be a number, got {p.get('max_years')!r}")
        self.max_age = int(p.get("max_age_days", 60) or 0)
        edu = str((p.get("applicant") or {}).get("education") or "")
        self.no_cs = bool(edu.strip()) and not CS_MINE.search(edu)  # empty education: unknown, no penalty
        self.min_score = int((p.get("quality") or {}).get("min_score", 3))
        self.open = {a.get("company", "").lower(): a for a in applications if a.get("stage") != "closed" and a.get("company")}
        self.open_roles = {same(a["company"], a.get("role") or "") for a in applications
                           if a.get("stage") != "closed" and a.get("company")}
        self.rejected = {a["company"].lower() for a in applications if a.get("company") and a.get("stage") == "closed"
                         and re.search(r"\brejected?\b|\bdeclined?\b|\bred\b|olumsuz|turned down", (a.get("status") or "") + (a.get("note") or ""), re.I)}

    def judge(self, j):
        """Returns (score 1-5 or 0 when dropped, reason, extra fields)."""
        t, loc, text = j["title"], j.get("location") or "", j.get("text") or ""
        if self.exclude and self.exclude.search(t):
            return 0, "excluded word: " + self.exclude.search(t).group(0).lower(), {}
        # many junior roles are titled plainly ("UX Designer"); those pass only when the text names a level or low years
        untitled = bool(self.seniority) and not self.seniority.search(t)
        if untitled and not (self.role_nouns and self.role_nouns.search(t)):
            return 0, "title lacks a seniority word", {}
        if callable(text):  # a board whose list has no description (smartrecruiters): fetched only now
            try:
                text = j["text"] = text() or ""
            except Exception:
                text = j["text"] = ""
        where = None
        if self.locations and not NO_PLACE.sub("", loc):  # no place named: look in the title, then the text, never drop
            m = self.locations.search(t) or self.locations.search(text)
            where = f"location from posting: {m.group(0)}" if m else "location unknown, check it"
        elif self.locations and not (self.locations.search(loc) or self.locations.search(t)):
            remote = j.get("remote") or REMOTE.search(loc)
            if not (remote and (self.want_remote or (self.countries and self.countries.search(loc)))):
                return 0, f"location: {loc or '?'}", {}
        only = self.locations and (ONLY.search(loc) or ONLY.search(t))
        limit = only and next(g for g in only.groups() if g)
        mine = [rx for rx in (self.locations, self.countries) if rx]
        if only and not any(rx.search(limit) or rx.search(REGIONS.get(limit.lower(), "")) for rx in mine):
            return 0, f"remote, {limit} only", {}
        if hit := said(self.breakers, text):
            return 0, "deal breaker: " + hit.group(0), {}
        years = [int(m.group(1)) if m.group(1).isdigit() else NUM[m.group(1).lower()] for m in YEARS.finditer(text) if not AGE.search(text[max(0, m.start() - 25):m.start()])]
        if years and max(years) > self.max_years and min(years) > self.max_years:
            return 0, f"asks for {min(years)}+ years", {}
        pts, why = 0, []
        if untitled:
            lvl = self.seniority.search(text)
            if not (years or lvl):
                return 0, "title lacks a seniority word and the text names no level or years", {}
            pts -= 1; why.append("no level in title, text says " + (lvl.group(0).lower() if lvl else f"{max(years)} years"))
        full = [r for r, ws in self.roles if all(w.search(t) for w in ws)]
        if full:
            pts += 2; why.append("role: " + ", ".join(full))
        elif self.role_nouns and self.role_nouns.search(t):
            pts += 1; why.append("role word: " + self.role_nouns.search(t).group(0).lower())
        elif self.role_nouns:
            return 0, "title: no target role", {}
        age = (self.today - day(j.get("posted"))).days if day(j.get("posted")) else None
        if self.max_age and age is not None and age > self.max_age:
            return 0, f"posted {age} days ago (max_age_days {self.max_age})", {}
        if where:
            why.append(where)
        if self.no_cs:
            asks = [text[max(0, m.start() - 80):m.end() + 80] for m in CS_DEGREE.finditer(text)]
            asks = [c for c in asks if not CS_OPTIONAL.search(c)]
            if any(not CS_SOFT.search(c) for c in asks):
                pts -= 1; why.append("needs a CS degree, yours is not")
            elif asks:
                why.append("CS degree or equivalent asked")
        have = [s for s, rx in self.skills.items() if rx.search(text) or rx.search(t)]
        if have:
            pts += min(2, len(have)); why.append("skills: " + ", ".join(have))
        if self.german is not None and (need := german_asked(text)) > self.german:
            pts -= 1; why.append(f"asks German {LEVEL[need]}, you have {LEVEL[self.german]}")
        if hit := said(self.strong, text):
            pts += 1; why.append("+" + hit.group(0))
        if hit := said(self.weak, text):
            pts -= 1; why.append("-" + hit.group(0))
        if age is not None and age > 90:
            pts -= 1; why.append(f"posted {age} days ago")
        elif age is not None and age <= 14:
            why.append("fresh")  # news, not fit: it must not lift a mediocre match to 5
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
                rec = dict(company=j["company"], role=j["title"], link=j["link"], location=j.get("location", ""), score=score, reason=why, posted=str(j.get("posted") or "")[:10],
                           text=(j.get("text") if isinstance(j.get("text"), str) else "")[:6000])  # menajer.py drafts from it
                seen[j["id"]] = dict(company=j["company"], role=j["title"], score=score, src=f"{src}/{slug}",
                                     first=old.get(j["id"], {}).get("first", today.isoformat()), last=today.isoformat())
                if score == 0:
                    if j["id"] not in old: dropped.append(dict(company=j["company"], role=j["title"], reason=why))
                    continue
                c = j["company"].lower()
                tracked = c in sc.open and (not sc.open[c].get("role") or same(j["company"], j["title"]) in sc.open_roles)
                if c in sc.open and not tracked:  # another role there: still a new posting
                    rec["reason"] += f"; you already applied there for {sc.open[c]['role']}"
                if tracked:
                    changed.append(dict(company=j["company"], what=f"already tracked ({sc.open[j['company'].lower()].get('stage')}): {j['title']} {score}/5"))
                elif j["id"] not in old:
                    (new if score >= sc.min_score else dropped).append(rec if score >= sc.min_score else dict(company=j["company"], role=j["title"], reason=f"{score}/5 under min_score: {why}"))
                elif old[j["id"]].get("score", 0) < sc.min_score <= score:
                    changed.append(dict(company=j["company"], what=f"now {score}/5 (was {old[j['id']].get('score')}): {j['title']}"))
    new.sort(key=lambda r: (-r["score"], r["posted"]))
    once = set()  # the same job on two boards or in two cities: keep the best-scored one
    new = [r for r in new if not (same(r["company"], r["role"]) in once or once.add(same(r["company"], r["role"])))]
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
