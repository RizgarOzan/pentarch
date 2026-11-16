# -*- coding: utf-8 -*-
"""Applications record and form check: the steps between a good posting and a sent application. Stdlib only.

    python -I tracker/apply.py list [--stage drafted]
    python -I tracker/apply.py todo [--max 2]          # new postings at min_score or better with no record yet (JSON lines)
    python -I tracker/apply.py add --company C --role R [--posting URL] [--stage watching] [--status TEXT] [--cv P] [--package P]
    python -I tracker/apply.py set ID STAGE [--status TEXT]
    python -I tracker/apply.py check FORM [--id ID]    # FORM: JSON {label: value} read back from a filled form, or plain text
    python -I tracker/apply.py approve ID --quote "the owner's own words"
    python -I tracker/apply.py sent ID

The flow it guards: an agent drafts a CV and letter (stage drafted), fills the form without submitting, runs `check`
on what it typed, shows the owner and waits. Only the owner's yes becomes `approve`, and `sent` refuses unless the
form passed `check` and was approved after that. check compares the form against the applicant block in profile.json
(setup.py "about you") and exits 1 on a wrong fact: another email or phone, a graduation year that isn't in your
education, a current employer you don't have, a sponsorship answer that contradicts yours, a link you don't own,
a placeholder like [number?] left from the CV draft.
--config defaults to tracker/config.json next to this file; profile.json is read from the same folder.
"""
import argparse, datetime, json, pathlib, re, sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import build  # noqa: E402  (config loading and the stage list)

def slug(*parts):
    return re.sub(r"[^a-z0-9]+", "-", " ".join(parts).lower()).strip("-")[:60]


class Book:
    def __init__(self, cfg, today=None):
        self.data = pathlib.Path(cfg["data_dir"])
        self.path = self.data / "applications.json"
        self.today = (today or datetime.date.today()).isoformat()
        self.rows = json.loads(self.path.read_text(encoding="utf-8-sig")) if self.path.exists() else []

    def save(self):
        self.data.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text("[\n" + ",\n".join("  " + json.dumps(r, ensure_ascii=False) for r in self.rows) + "\n]\n", encoding="utf-8")
        tmp.replace(self.path)

    def find(self, id_):
        for r in self.rows:
            if r.get("id") == id_:
                return r
        sys.exit(f"no application with id {id_!r}; see: apply.py list")

    def add(self, company, role, stage="watching", **extra):
        if stage not in build.STAGES or stage == "sent":
            sys.exit(f"stage must be one of {', '.join(s for s in build.STAGES if s != 'sent')} (sent only through approve + sent)")
        id_ = extra.pop("id", None) or slug(company, role)
        row = next((r for r in self.rows if r.get("id") == id_), None)
        if row is None:
            row = dict(id=id_, company=company, role=role, added=self.today)
            self.rows.append(row)
        row.update({k: v for k, v in extra.items() if v not in (None, "")}, stage=stage, checked=self.today)
        return row

    def set(self, id_, stage, status=None):
        if stage not in build.STAGES or stage == "sent":
            sys.exit("use `approve` and `sent` to mark an application sent" if stage == "sent" else f"unknown stage {stage}")
        r = self.find(id_)
        r.update(stage=stage, checked=self.today, **({"status": status} if status else {}))
        return r

    def todo(self, scan, min_score, limit):
        """New postings worth a draft: in scan.json's new list, at min_score or better, no record for the same link or id."""
        links = {r.get("posting") for r in self.rows}
        ids = {r.get("id") for r in self.rows}
        out = [dict(id=slug(j["company"], j["role"]), **j) for j in scan.get("new", [])
               if j.get("score", 0) >= min_score and j.get("link") not in links]
        return [j for j in out if j["id"] not in ids][:limit]

    def approve(self, id_, quote):
        r = self.find(id_)
        if not r.get("awaiting"):
            sys.exit(f"{id_}: the form hasn't passed `check --id {id_}` yet; fill it, check it, show it, then ask")
        if not quote.strip():
            sys.exit("--quote must hold the owner's own words of approval")
        r.update(approved_on=datetime.datetime.now().isoformat(timespec="seconds"), approval=quote.strip())
        return r

    def sent(self, id_):
        r = self.find(id_)
        if not (r.get("awaiting") and r.get("approved_on") and r["approved_on"] >= r["awaiting"]):
            sys.exit(f"{id_}: not approved after the last form check; nothing recorded")
        r.update(stage="sent", sent_on=self.today, checked=self.today, status="Sent after approval")
        r.pop("awaiting", None)
        return r


# ---- form check -------------------------------------------------------------------------------------------------

YES = re.compile(r"^\s*(yes|y|true|evet|e)\b", re.I)
NO = re.compile(r"^\s*(no|n|false|hayır|hayir|h)\b", re.I)
NONE = re.compile(r"^\s*(-|—|none|n/?a|no|yok|hiçbiri|student|öğrenci|unemployed|not employed|çalışmıyorum)?\s*$", re.I)
PLACEHOLDER = re.compile(r"\[[^\]\n]{0,40}\?\]|\{\{|\bTODO\b|\bTBD\b|lorem ipsum|<your [a-z ]+>", re.I)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
YEAR = re.compile(r"\b(19[5-9]\d|20[0-6]\d)\b")


def digits(s): return re.sub(r"\D", "", str(s or ""))
def url(s): return re.sub(r"^(https?://)?(www\.)?", "", str(s or "").strip().lower()).rstrip("/")
def words(s): return set(re.findall(r"\w+", str(s or "").lower()))


def check_form(form, ap):
    """form: {label: value} or plain text. ap: the applicant block. Returns a list of (label, problem)."""
    bad = []
    if isinstance(form, str):  # a letter or a pasted page: only what can be judged without labels
        items = [("text", form)]
        for m in re.finditer(r"graduat\w*[^\n.]{0,40}?\b(\d{4})\b|mezun\w*[^\n.]{0,40}?\b(\d{4})\b", form, re.I):
            y = m.group(1) or m.group(2)
            if ap.get("education") and y not in YEAR.findall(ap["education"]):
                bad.append(("text", f"graduation year {y} is not in your education ({ap['education']})"))
        cur = re.search(r"(?:current(?:ly)?\s+(?:working|employed)\s+(?:at|with)|my current (?:employer|company) is)\s+([A-Z][\w&.-]*(?:\s+[A-Z][\w&.-]*)*)", form)
        if cur and "current_employer" in ap and not (ap["current_employer"] and words(cur.group(1)) & words(ap["current_employer"])):
            bad.append(("text", f"says you work at {cur.group(1)} now; your current employer is {ap.get('current_employer') or 'none'}"))
    else:
        items = [(str(k), "" if v is None else str(v)) for k, v in form.items()]
    for label, value in items:
        L = label.lower()
        if m := PLACEHOLDER.search(value):
            bad.append((label, f"placeholder left in: {m.group(0)}"))
        for e in EMAIL.findall(value):
            if ap.get("email") and e.lower() != ap["email"].strip().lower():
                bad.append((label, f"email {e} is not yours ({ap['email']})"))
        if label == "text":
            continue
        if re.search(r"phone|mobile|telefon|cep", L) and value.strip() and ap.get("phone"):
            a, b = digits(value), digits(ap["phone"])
            if a[-9:] != b[-9:]:
                bad.append((label, f"phone {value} is not yours ({ap['phone']})"))
        if re.search(r"(^|\b)(full |first |last |given |family |sur)?name\b|ad[ıi] ?soyad|^ad$|^soyad", L) \
                and not re.search(r"company|employer|school|university|referr|reference|manager|şirket|okul", L) \
                and value.strip() and ap.get("full_name") and not words(value) <= words(ap["full_name"]):
            bad.append((label, f"name {value!r} is not part of {ap['full_name']!r}"))
        if re.search(r"graduat|mezun", L) and ap.get("education"):
            for y in YEAR.findall(value):
                if y not in YEAR.findall(ap["education"]):
                    bad.append((label, f"graduation year {y} is not in your education ({ap['education']})"))
        # an older profile without the key: unknown, so not judged (the apply skill asks instead)
        if "current_employer" in ap and re.search(r"current(ly)?\s*(company|employer)|present employer|şu anki (şirket|işveren)|mevcut işveren", L):
            mine = ap.get("current_employer", "")
            if mine and not NONE.match(value) and not words(value) & words(mine):
                bad.append((label, f"current employer {value!r}; yours is {mine!r}"))
            elif not mine and not NONE.match(value):
                bad.append((label, f"current employer {value!r}, but you have none (leave it empty or write student)"))
        if re.search(r"sponsor|vize|visa", L) and NO.match(ap.get("needs_sponsorship", "")) and YES.match(value):
            bad.append((label, "says you need sponsorship; your answer is no"))
        if re.search(r"sponsor|vize|visa", L) and YES.match(ap.get("needs_sponsorship", "")) and NO.match(value):
            bad.append((label, "says you don't need sponsorship; your answer is yes"))
        if re.search(r"linkedin|github|portfolio|website|portfolyo", L) and value.strip():
            mine = {url(x) for x in ap.get("links") or []}
            if mine and url(value) not in mine:
                bad.append((label, f"link {value} is not one of yours"))
        if re.search(r"salary|compensation|maaş|ücret", L) and ap.get("salary") and digits(value):
            if not set(re.findall(r"\d+", value.replace(",", "").replace(".", ""))) & set(re.findall(r"\d+", ap["salary"].replace(",", "").replace(".", ""))):
                bad.append((label, f"salary {value} differs from your answer ({ap['salary']})"))
    return bad


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--config", default=str(HERE / "config.json") if (HERE / "config.json").exists() else None)
    ap.add_argument("--profile"); ap.add_argument("--today")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list"); p.add_argument("--stage")
    p = sub.add_parser("todo"); p.add_argument("--max", type=int, default=2)
    p = sub.add_parser("add")
    for k in ("company", "role"): p.add_argument("--" + k, required=True)
    for k in ("id", "posting", "status", "cv", "package", "location", "deadline", "note"): p.add_argument("--" + k)
    p.add_argument("--stage", default="watching"); p.add_argument("--score", type=int)
    p = sub.add_parser("set"); p.add_argument("id"); p.add_argument("stage"); p.add_argument("--status")
    p = sub.add_parser("check"); p.add_argument("form"); p.add_argument("--id")
    p = sub.add_parser("approve"); p.add_argument("id"); p.add_argument("--quote", required=True)
    p = sub.add_parser("sent"); p.add_argument("id")
    a = ap.parse_args(argv)
    cfg = build.load_config(a.config)
    book = Book(cfg, datetime.date.fromisoformat(a.today) if a.today else None)
    prof_path = pathlib.Path(a.profile) if a.profile else pathlib.Path(a.config).parent / "profile.json" if a.config else HERE / "profile.json"
    profile = json.loads(prof_path.read_text(encoding="utf-8-sig")) if prof_path.exists() else {}

    if a.cmd == "list":
        for r in book.rows:
            if not a.stage or r.get("stage") == a.stage:
                print(f"{r.get('id')}\t{r.get('stage')}\t{r.get('company')} · {r.get('role')}\t{r.get('status', '')}")
        return 0
    if a.cmd == "todo":
        scan_p = book.data / "scan.json"
        scan = json.loads(scan_p.read_text(encoding="utf-8")) if scan_p.exists() else {}
        for j in book.todo(scan, (profile.get("quality") or {}).get("min_score", 3), a.max):
            print(json.dumps(j, ensure_ascii=False))
        return 0
    if a.cmd == "check":
        raw = sys.stdin.read() if a.form == "-" else pathlib.Path(a.form).read_text(encoding="utf-8-sig")
        try:
            form = json.loads(raw)
        except ValueError:
            form = raw
        if not isinstance(form, (dict, str)):
            sys.exit("FORM must be a JSON object {label: value} or plain text")
        applicant = profile.get("applicant") or {}
        if not any(v for k, v in applicant.items() if k != "_"):
            sys.exit(f"no applicant block in {prof_path}; run setup.py (about you) first")
        bad = check_form(form, applicant)
        for label, why in bad:
            print(f"FAIL {label}: {why}")
        if bad:
            return 1
        print(f"ok: {len(form) if isinstance(form, dict) else 'text'} checked against {prof_path.name}")
        if a.id:
            book.find(a.id).update(awaiting=datetime.datetime.now().isoformat(timespec="seconds"),
                                   status="Form filled and checked, waiting for your approval")
            book.find(a.id).pop("approved_on", None)
            book.save()
        return 0
    if a.cmd == "add":
        extra = {k: getattr(a, k) for k in ("id", "posting", "status", "cv", "package", "location", "deadline", "note", "score")}
        r = book.add(a.company, a.role, a.stage, **extra)
    elif a.cmd == "set":
        r = book.set(a.id, a.stage, a.status)
    elif a.cmd == "approve":
        r = book.approve(a.id, a.quote)
    else:
        r = book.sent(a.id)
    book.save()
    print(f"{r['id']}: {r['stage']}" + (f" ({r['status']})" if r.get("status") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
