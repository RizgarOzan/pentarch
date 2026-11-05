# -*- coding: utf-8 -*-
"""CV checker for the Pentarch cv skill. Standard library only, no model, no network.

    python cv.py check cv.md [--jd posting.txt] [--lang en|tr]   rule checks, FAIL/WARN/PASS lines
    python cv.py template                                       the single-column markdown skeleton

The CV is markdown in the shape `template` prints: `# Name`, one contact line, `## SECTION` headings,
`**Title**` entry lines with the date on the right, `- ` bullets. Rules come from four sources, named
in SKILL.md: Bock's XYZ formula, Harvard's resume guide, HRBrain's ATS tips and Jake's Resume template.
Exit code 1 when a check FAILs, else 0.
"""
import argparse, re, sys

HEADINGS = {  # what an ATS parser labels without guessing (HRBrain); Jake's and Harvard's samples use the same names
    "experience", "work experience", "professional experience", "education", "skills", "technical skills",
    "projects", "certifications", "publications", "leadership", "summary", "awards",
    "deneyim", "iş deneyimi", "eğitim", "beceriler", "teknik beceriler", "projeler", "sertifikalar", "özet",
}
DATE = r"(?:Jan|Feb|Mar|Apr|May|June?|July?|Aug|Sept?|Oct|Nov|Dec)\.? \d{4}|\d{4}|Present|Current|Halen"
DATE_RX = re.compile(rf"({DATE})\s*(?:--|-|–|—)\s*({DATE})", re.I)
MONTHS = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}
WEAK = ("responsible for", "member of", "worked as", "worked on", "duties included", "participated in", "assisted with",
        "assisted in", "helped with", "helped to", "involved in", "tasked with", "sorumluydum", "görev aldım", "yer aldım")
WEAK_FIRST = {"participated", "assisted", "utilized", "studied", "worked", "helped", "involved", "tasked", "used", "learned"}
PAST_IRREGULAR = {"led", "built", "wrote", "ran", "won", "sold", "taught", "made", "grew", "cut", "set", "spoke", "drove",
                  "took", "brought", "oversaw", "rewrote", "began", "became", "held", "found", "kept", "put", "read",
                  "shrank", "sped", "split", "spent", "stood", "undertook", "upheld", "withdrew", "co-led", "co-founded"}
QUALIFIERS = re.compile(r"\b(beginner|intermediate|basic|novice|entry[- ]level|familiar with|working knowledge)\b", re.I)
OBVIOUS = re.compile(r"\b(Microsoft Word|MS Word|Excel|PowerPoint|Windows|macOS|VS ?Code|Google Docs|email)\b", re.I)
SOFT = re.compile(r"\b(team ?player|hard[- ]working|leadership|communication skills|problem[- ]solving|detail[- ]oriented|"
                  r"fast learner|self[- ]motivated|takım oyuncusu|iletişim becerileri)\b", re.I)
PRONOUN = re.compile(r"\b(I|I'm|I've|me|my|we|we're|our|ben|biz|benim|bizim)\b")
PASSIVE = re.compile(r"\b(was|were|been|is|are|being)\s+(\w+ed|built|led|made|written|chosen|given|taken|run)\b", re.I)
STOP = set("the a an and or of to in on for with by at as is are be from this that these those you your we our will can "
           "must have has had not but it its into than who what which their they them were was been being about across "
           "while also any all more most other such per via over under new strong good great able work working team role "
           "job position candidate experience years year ability skills skill required requirements preferred qualifications "
           "responsibilities including include includes etc".split())


def read(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return f.read()
    except OSError as e:
        raise SystemExit(f"cannot read {path}: {e}")


def parse(text):
    """Sections as [(heading, [lines])]; the part before the first heading is the header."""
    sections, cur = [("", [])], None
    for raw in text.splitlines():
        line = raw.rstrip()
        m = re.match(r"^#{2,3}\s+(.+?)\s*#*$", line)
        if m:
            cur = (m.group(1).strip(), [])
            sections.append(cur)
        elif line.strip():
            (cur or sections[0])[1].append(line)
    return sections


def entries(lines):
    """Groups a section's lines into entries: each `**Title**` line opens one; bullets attach to it."""
    out = []
    for line in lines:
        s = line.strip()
        if s.startswith("**"):
            out.append({"title": s, "dates": DATE_RX.search(s), "bullets": [], "lines": [s]})
        elif s.startswith(("- ", "* ", "• ")):
            if not out:
                out.append({"title": "", "dates": None, "bullets": [], "lines": []})
            out[-1]["bullets"].append(s[2:].strip())
        elif out:
            out[-1]["lines"].append(s)
            out[-1]["dates"] = out[-1]["dates"] or DATE_RX.search(s)
    return out


def first_word(bullet):
    return re.sub(r"[^\w'-]", "", bullet.split(" ", 1)[0]).lower()


def is_past(word):
    return word.endswith("ed") or word in PAST_IRREGULAR


def date_key(m):
    """Sort key for a date match: the end date, Present last."""
    end = m.group(2)
    if end.lower() in ("present", "current", "halen"):
        return (9999, 13)
    yr = int(re.search(r"\d{4}", end).group(0))
    mo = MONTHS.get(end[:3].lower(), 0)
    return (yr, mo)


def jd_keywords(jd):
    """Words the posting repeats or capitalises mid-sentence: the terms an ATS filter is most likely set on."""
    words = re.findall(r"[A-Za-z][\w+#.-]{1,}", jd)
    count = {}
    weight = 1  # a term under "preferred" counts triple, under "requirements" double, under "responsibilities" once (2026 hiring)
    for line in jd.splitlines():
        low = line.lower()
        if re.search(r"preferred|nice to have|bonus|\bplus\b|tercih", low):
            weight = 3
        elif re.search(r"requirement|qualification|must have|what you bring|aranan|gereksinim", low):
            weight = 2
        elif re.search(r"responsibilit|what you.ll do|you will|görev|sorumluluk", low):
            weight = 1
        for w in re.findall(r"[A-Za-z][\w+#.-]{1,}", line):
            k = w.lower().strip(".-")
            if len(k) < 3 or k in STOP:
                continue
            count[k] = count.get(k, 0) + weight
    caps = {w.lower().strip(".-") for w in re.findall(r"(?<=[a-z,;(] )[A-Z][\w+#.-]+", jd)} - STOP
    tech = {w.lower().strip(".-") for w in words if re.search(r"[A-Z].*[A-Z]|\d|[+#.]", w)} - STOP
    picked = {k for k, c in count.items() if c >= 2 and jd.lower().count(k) >= 2} | caps | tech
    return sorted(picked, key=lambda k: -count.get(k, 0))[:40]


def check_text(text, jd=None, lang="en"):
    """Returns a list of (level, message); level is PASS, WARN or FAIL."""
    out = []
    if not text.strip():
        return [("FAIL", "empty file")]
    if re.search(r"^\s*\|.*\|\s*$", text, re.M) or "<table" in text.lower():
        out.append(("FAIL", "table found; ATS parsers read tables out of order (HRBrain)"))
    if re.search(r"!\[|<img", text):
        out.append(("FAIL", "image found; photos, icons and logos are skipped or break parsing (HRBrain, Harvard)"))
    if re.search(r"\b(age|yaş|date of birth|doğum tarihi|gender|cinsiyet|married|evli|references available)\b", text, re.I):
        out.append(("WARN", "age, gender, birth date or references line; leave those out (Harvard)"))

    sections = parse(text)
    header = " ".join(sections[0][1])
    if not re.search(r"[\w.+-]+@[\w-]+\.\w+", header):
        out.append(("FAIL", "no email before the first heading; put name, phone and email in the body, not a page header (Harvard, HRBrain)"))
    if not re.search(r"\+?\d[\d\s().-]{7,}\d", header):
        out.append(("WARN", "no phone number in the contact line (Harvard)"))
    if not re.search(r"linkedin\.com/in/|github\.com/", header, re.I):
        out.append(("WARN", "no LinkedIn or GitHub link in the contact line (Jake's, Pirate King)"))

    heads = [h for h, _ in sections[1:]]
    if not heads:
        out.append(("FAIL", "no `## SECTION` headings"))
    for h in heads:
        if h.lower() not in HEADINGS:
            out.append(("FAIL", f"heading '{h}' is not one an ATS labels; use Experience, Education, Projects, Skills or Certifications (HRBrain)"))
    low = [h.lower() for h in heads]
    if "summary" in low or "özet" in low:
        out.append(("WARN", "summary section; drop it unless you are changing careers, the first bullets do its job (Pirate King, 2026 video)"))
    exp_i = next((i for i, h in enumerate(low) if "experience" in h or "deneyim" in h), None)
    edu_i = next((i for i, h in enumerate(low) if h in ("education", "eğitim")), None)
    if exp_i is None:
        out.append(("WARN", "no Experience section; projects count, but name the section Experience if any of it was paid"))
    if exp_i is not None and edu_i is not None:
        out.append(("PASS", "Education before Experience, Jake's order for students" if edu_i < exp_i else
                    "Experience before Education, the order once you have a job history (Pirate King)"))

    verbs, all_bullets, date_order = {}, 0, []
    for head, lines in sections[1:]:
        hl = head.lower()
        for line in lines:
            if re.match(rf"^(?:{DATE})\b", line.strip(), re.I):
                out.append(("WARN", f"line starts with a date: '{line.strip()[:40]}'; lead with the title, date on the right (Harvard)"))
        if hl in ("skills", "technical skills", "beceriler", "teknik beceriler"):
            body = " ".join(lines)
            if OBVIOUS.search(body):
                out.append(("WARN", f"obvious tool in skills ({OBVIOUS.search(body).group(0)}); it costs space and says nothing (Pirate King)"))
            if SOFT.search(body):
                out.append(("WARN", f"soft skill listed ({SOFT.search(body).group(0)}); show it in a bullet with a team size or result instead (2026 video)"))
            if QUALIFIERS.search(body):
                out.append(("WARN", f"skill-level label ({QUALIFIERS.search(body).group(0)}); list the skill or leave it out (Pirate King)"))
            continue
        for e in entries(lines):
            m = re.match(r"\*\*(.+?)\*\*", e["title"])
            name = (m.group(1) if m else head)[:40]
            bl = e["bullets"]
            all_bullets += len(bl)
            if e["title"] and not e["dates"] and hl not in ("certifications", "sertifikalar"):
                out.append(("WARN", f"'{name}': no 'Mon. YYYY -- Mon. YYYY' date; recruiters scan dates first (Jake's)"))
            if e["dates"]:
                date_order.append((head, name, date_key(e["dates"])))
            if hl in ("experience", "work experience", "professional experience", "projects", "deneyim", "iş deneyimi", "projeler"):
                if not bl:
                    out.append(("WARN", f"'{name}': no bullets; 3 to 5 lines, each with a result (Simplify, Jake's)"))
                elif len(bl) > 5:
                    out.append(("WARN", f"'{name}': {len(bl)} bullets; keep 3 to 5, cut the weakest (Simplify)"))
                elif len(bl) < 3 and e["dates"] and date_key(e["dates"])[0] == 9999:
                    out.append(("WARN", f"'{name}': only {len(bl)} bullets for the current role; 3 to 5 (Simplify)"))
            current = bool(e["dates"]) and date_key(e["dates"])[0] == 9999
            for i, b in enumerate(bl):
                fw = first_word(b)
                tag = f"'{name}' bullet {i + 1}"
                if PRONOUN.search(b):
                    out.append(("FAIL", f"{tag}: pronoun ({PRONOUN.search(b).group(0)}); bullets have no subject (Harvard)"))
                if any(w in b.lower() for w in WEAK):
                    out.append(("FAIL", f"{tag}: '{next(w for w in WEAK if w in b.lower())}' describes a duty; write what changed and by how much (Bock)"))
                if lang == "en":
                    if PASSIVE.search(b):
                        out.append(("WARN", f"{tag}: passive voice ('{PASSIVE.search(b).group(0)}'); start with the verb (Harvard)"))
                    if fw in WEAK_FIRST:
                        out.append(("WARN", f"{tag}: starts with '{fw}'; a stronger verb says what you did (Bock, Harvard lists it but marks it weak)"))
                    elif not current and not is_past(fw):
                        out.append(("WARN", f"{tag}: '{fw}' is not past tense; finished roles are past tense (Jake's, Harvard)"))
                    elif current and is_past(fw) and any(not is_past(first_word(x)) for x in bl):
                        out.append(("WARN", f"{tag}: mixes past and present tense inside one entry; pick one per entry (Simplify)"))
                    verbs.setdefault(fw, []).append(tag)
                if not re.search(r"\d", b):
                    out.append(("FAIL" if i == 0 else "WARN", f"{tag}: no number; " + ("the first bullet of an entry must carry a metric (2026 video)" if i == 0 else "a %, $, count, team size or time span (Bock)")))
                if b.rstrip().endswith("."):
                    out.append(("WARN", f"{tag}: ends with a period; bullets carry none (Jake's)"))
                if len(b) > 220:
                    out.append(("WARN", f"{tag}: {len(b)} chars; over two lines, split or cut"))
    for fw, tags in verbs.items():
        if len(tags) > 1 and fw not in WEAK_FIRST:
            out.append(("WARN", f"verb '{fw}' opens {len(tags)} bullets; use each verb once (Simplify, Harvard)"))
    for (h1, n1, k1), (h2, n2, k2) in zip(date_order, date_order[1:]):
        if h1 == h2 and k2 > k1:
            out.append(("WARN", f"'{n2}' is newer than '{n1}' but comes after it; newest first inside a section (Harvard)"))
    n_lines = sum(len(l) for _, l in sections)
    if n_lines > 60 or len(text) > 4200:
        out.append(("WARN", f"{n_lines} lines, {len(text)} chars; that is more than one page at 10-12 pt (Jake's, Harvard samples)"))
    if re.search(r"[★☆✓✔➤►▪●◆■♦]", text):
        out.append(("WARN", "decorative glyphs; some parsers drop the line (HRBrain)"))

    if jd:
        kws = jd_keywords(jd)
        if kws:
            cv_low = text.lower()
            hit = [k for k in kws if k in cv_low]
            miss = [k for k in kws if k not in cv_low]
            pct = 100 * len(hit) // len(kws)
            out.append(("WARN" if pct < 50 else "PASS", f"posting keywords: {len(hit)}/{len(kws)} present ({pct}%)" + (f"; missing: {', '.join(miss[:15])}" if miss else "")))
            out.append(("PASS", "only add a missing keyword where it is true; a bare keyword list reads as stuffing (HRBrain)"))
    if not out:
        out.append(("PASS", "no rule hit"))
    return out


TEMPLATE = """# FULL NAME
+1 555 000 0000 | name@mail.com | linkedin.com/in/name | github.com/name

## EDUCATION
**University Name**                                   City, Country
*B.Sc. in Something*                                  Sept. 2021 -- June 2025

## EXPERIENCE
**Job Title**                                         Mar. 2025 -- Present
*Employer*                                            City, Country
- Verb + what you built + measurable outcome (first bullet carries the biggest number)
- Verb + what + tech + result
- Verb + what + result

**Job Title**                                         June 2024 -- Feb. 2025
*Employer*                                            City, Country
- Verb + what + result
- Verb + what + result
- Verb + what + result

## PROJECTS
**Project Name** | *Language, Framework, Tool*         Jan. 2025 -- Present
- Verb + what + result (link in the title if it is public)
- Verb + what + result

## TECHNICAL SKILLS
**Languages**: ...
**Frameworks**: ...
**Developer Tools**: ...
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("file"); c.add_argument("--jd", help="the job posting as text"); c.add_argument("--lang", default="en", choices=["en", "tr"])
    sub.add_parser("template")
    a = ap.parse_args(argv)
    if a.cmd == "template":
        print(TEMPLATE, end="")
        return 0
    rows = check_text(read(a.file), read(a.jd) if a.jd else None, a.lang)
    for lvl, msg in rows:
        print(f"{lvl:4} {msg}")
    fails = sum(l == "FAIL" for l, _ in rows)
    print(f"{fails} FAIL, {sum(l == 'WARN' for l, _ in rows)} WARN")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
