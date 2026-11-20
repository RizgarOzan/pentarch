# -*- coding: utf-8 -*-
"""Tests for scan.py with fake boards: no network.  python -I tracker/test_scan.py"""
import datetime, json, pathlib, sys, tempfile, unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import scan

TODAY = datetime.date(2026, 11, 5)
PROFILE = {
    "target_roles": ["Junior Software Engineer", "Game Developer"],
    "seniority": ["intern", "junior", "entry level"],
    "locations": ["Remote", "Berlin"],
    "skills": ["Python", "C#", "Unity"],
    "signals": {"strong": ["mentorship"], "weak": ["unpaid"], "deal_breakers": ["security clearance"]},
    "max_years": 2,
    "quality": {"min_score": 3},
    "boards": {"greenhouse": ["acme"], "ashby": ["zed"]},
}


def job(id, title, loc="Remote", text="", posted="2026-11-01", company="Acme", remote=False):
    return dict(id=id, company=company, title=title, location=loc, remote=remote, posted=posted, link=f"https://x/{id}", text=text)


class Judge(unittest.TestCase):
    def setUp(self):
        self.s = scan.Scorer(PROFILE, [], TODAY)

    def test_senior_and_non_entry_titles_drop(self):
        self.assertEqual(self.s.judge(job("1", "Senior Junior Engineer"))[0], 0)
        self.assertEqual(self.s.judge(job("2", "Software Engineer"))[0], 0)
        self.assertEqual(self.s.judge(job("3", "Engineering Manager, Junior Team"))[0], 0)

    def test_location_rules(self):
        self.assertEqual(self.s.judge(job("1", "Junior Software Developer", loc="Austin, TX"))[0], 0)
        self.assertGreater(self.s.judge(job("2", "Junior Software Developer", loc="Berlin, Germany"))[0], 0)
        self.assertGreater(self.s.judge(job("3", "Junior Software Developer", loc="Austin, TX", remote=True))[0], 0)
        self.assertGreater(self.s.judge(job("4", "Junior Software Developer", loc="Anywhere (EMEA)"))[0], 0)

    def test_negated_signals_do_not_count(self):
        pro = dict(PROFILE, signals={"strong": ["visa sponsorship"], "weak": [], "deal_breakers": ["security clearance"]})
        sc = scan.Scorer(pro, [], TODAY)
        t = "Junior Software Engineer"
        _, why, _ = sc.judge(job("1", t, text="We are unable to offer visa sponsorship."))
        self.assertNotIn("+visa sponsorship", why)
        _, why, _ = sc.judge(job("2", t, text="We offer visa sponsorship."))
        self.assertIn("+visa sponsorship", why)
        self.assertGreater(sc.judge(job("3", t, text="No security clearance required."))[0], 0)
        self.assertEqual(sc.judge(job("4", t, text="Security clearance required."))[0], 0)

    def test_years_written_as_words(self):
        s, why, _ = self.s.judge(job("1", "Junior Software Developer", text="At least three years of experience with Python."))
        self.assertEqual(s, 0)

    def test_remote_us_is_open_to_someone_living_in_the_us(self):
        pro = dict(PROFILE, locations=["Austin", "remote"], applicant={"city": "Austin, USA"})
        sc = scan.Scorer(pro, [], TODAY)
        self.assertGreater(sc.judge(job("1", "Junior Software Developer", loc="Remote - US"))[0], 0)
        self.assertGreater(sc.judge(job("2", "Junior Software Developer", loc="Remote (United States)"))[0], 0)
        self.assertEqual(sc.judge(job("3", "Junior Software Developer", loc="Remote - Canada"))[0], 0)

    def test_deal_breakers_and_years(self):
        self.assertIn("deal breaker", self.s.judge(job("1", "Junior Software Developer", text="Requires active security clearance."))[1])
        self.assertIn("5+ years", self.s.judge(job("2", "Junior Software Developer", text="You have 5+ years of experience."))[1])
        # a range that starts under the limit is fine
        self.assertGreater(self.s.judge(job("3", "Junior Software Developer", text="1-3 years of experience with 5 years of Python not required"))[0], 0)

    def test_score_adds_up(self):
        s, why, extra = self.s.judge(job("1", "Junior Software Engineer", text="Python and C# with Unity; strong mentorship culture.", posted="2026-11-01"))
        self.assertEqual(s, 5)  # 1 + role 2 + skills 2 + strong 1 + fresh 1 = 7, capped at 5
        for part in ("role:", "skills: Python, C#, Unity", "+mentorship", "fresh"):
            self.assertIn(part, why)
        s2, why2, _ = scan.Scorer(dict(PROFILE, max_age_days=365), [], TODAY).judge(job("2", "Intern Game Tester (QA)", text="Unpaid position.", posted="2026-06-01"))
        self.assertEqual(s2, 1)  # 1 + role 2 - weak 1 - old 1 → clamped to 1
        self.assertIn("role: Game Developer", why2); self.assertIn("-Unpaid", why2); self.assertIn("days ago", why2)

    def test_location_that_names_no_place(self):
        # Peak's Lever board puts "Full-time" in the location field: look in the title and text, never drop
        s, why, _ = self.s.judge(job("1", "Junior Game Developer", loc="Full-time", text="Join our Berlin studio."))
        self.assertGreater(s, 0); self.assertIn("location from posting: Berlin", why)
        s, why, _ = self.s.judge(job("2", "Junior Game Developer", loc=""))
        self.assertGreater(s, 0); self.assertIn("location unknown", why)
        self.assertEqual(self.s.judge(job("3", "Junior Game Developer", loc="Austin, TX"))[0], 0)  # a real place still drops

    def test_old_postings_drop(self):
        s, why, _ = self.s.judge(job("1", "Junior Software Engineer", posted="2021-07-21"))
        self.assertEqual(s, 0); self.assertIn("days ago (max_age_days 60)", why)
        self.assertGreater(self.s.judge(job("2", "Junior Software Engineer", posted="2026-09-10"))[0], 0)  # 56 days
        self.assertGreater(scan.Scorer(dict(PROFILE, max_age_days=0), [], TODAY).judge(job("3", "Junior Software Engineer", posted="2021-07-21"))[0], 0)

    def test_cs_degree_requirement(self):
        mis = scan.Scorer(dict(PROFILE, applicant={"education": "X University, Management Information Systems, 2027"}), [], TODAY)
        hard, soft, pref = ("BS in Computer Science required.", "BS in Computer Science or equivalent experience.",
                            "A degree in Computer Science is preferred.")
        base = mis.judge(job("0", "Junior Software Engineer"))[0]
        s, why, _ = mis.judge(job("1", "Junior Software Engineer", text=hard))
        self.assertEqual(s, base - 1); self.assertIn("needs a CS degree", why)
        s, why, _ = mis.judge(job("2", "Junior Software Engineer", text=soft))
        self.assertEqual(s, base); self.assertIn("CS degree or equivalent", why)
        self.assertNotIn("CS degree", mis.judge(job("3", "Junior Software Engineer", text=pref))[1])
        edu = scan.Scorer(dict(PROFILE, applicant={"education": "Z University, B.S. Computer Education and Instructional Technology"}), [], TODAY)
        self.assertIn("needs a CS degree", edu.judge(job("6", "Junior Software Engineer", text=hard))[1])
        cs = scan.Scorer(dict(PROFILE, applicant={"education": "Y University, Computer Engineering"}), [], TODAY)
        self.assertNotIn("CS degree", cs.judge(job("4", "Junior Software Engineer", text=hard))[1])
        self.assertNotIn("CS degree", self.s.judge(job("5", "Junior Software Engineer", text=hard))[1])  # education unknown

    def test_role_words_must_match_the_title(self):
        s = scan.Scorer(dict(PROFILE, target_roles=["Product Designer"], seniority=[]), [], TODAY)
        self.assertIn("role: Product Designer", s.judge(job("1", "Junior Product Designer"))[1])
        self.assertIn("role word: design", s.judge(job("2", "UX Designer"))[1])  # "design" also finds "Digital Design"
        self.assertEqual(s.judge(job("3", "Product Support Specialist")), (0, "title: no target role", {}))

    def test_software_engineer_also_finds_developer_titles(self):
        s = scan.Scorer(dict(PROFILE, target_roles=["junior software engineer"]), [], TODAY)
        self.assertGreater(s.judge(job("1", "Junior Backend Developer (m/w/d)"))[0], 0)
        self.assertGreater(s.judge(job("2", "Junior Backend Entwickler (m/w/d)"))[0], 0)
        self.assertEqual(s.judge(job("3", "Junior Sales Manager"))[0], 0)

    def test_rejection_feedback(self):
        apps = [{"company": "Acme", "stage": "closed", "status": "rejected after interview"}]
        s = scan.Scorer(PROFILE, apps, TODAY)
        self.assertIn("rejected you before", s.judge(job("1", "Junior Software Engineer", text="Python"))[1])

    def test_default_exclude_and_seniority_synonyms(self):
        p = dict(PROFILE, exclude=None, seniority=["entry level"])
        s = scan.Scorer(p, [], TODAY)
        self.assertGreater(s.judge(job("1", "New Grad Software Engineer"))[0], 0)
        self.assertEqual(s.judge(job("2", "Staff Engineer, New Grad Program"))[0], 0)

    def test_turkish_internship_words(self):
        s = scan.Scorer(dict(PROFILE, target_roles=["yazılım"], seniority=["intern"]), [], TODAY)
        for title in ("Yazılım Stajyeri", "Yazılım Staj Programı 2027", "Yazılım Yaz Stajı"):
            self.assertGreater(s.judge(job(title, title))[0], 0, title)
        self.assertEqual(s.judge(job("x", "Senior Yazılım Mühendisi"))[0], 0)

    def test_german_postings(self):
        p = dict(PROFILE, target_roles=["Werkstudent Software"], seniority=["intern"], locations=["Berlin"],
                 applicant={"education": "TU Berlin, B.Sc. Informatik"})
        s = scan.Scorer(p, [], TODAY)
        sc, why, _ = s.judge(job("1", "Werkstudent (m/w/d) Softwareentwicklung", loc="Berlin"))
        self.assertGreater(sc, 0); self.assertIn("role: Werkstudent Software", why)  # level word dropped, compound matched
        self.assertGreater(s.judge(job("2", "Werkstudierende Software Engineering", loc="Headquarters"))[0], 0)
        self.assertGreater(s.judge(job("3", "Werkstudent Software (Berlin)", loc="Hamburg, Berlin"))[0], 0)
        self.assertEqual(s.judge(job("4", "Werkstudent Software", loc="München"))[0], 0)
        self.assertIn("3+ years", s.judge(job("5", "Werkstudent Software", loc="Berlin", text="Mindestens 3 Jahre Berufserfahrung"))[1])
        self.assertNotIn("CS degree", s.judge(job("6", "Werkstudent Software", loc="Berlin", text="Studium der Informatik required."))[1])
        self.assertEqual(s.judge(job("7", "Werkstudent Marketing", loc="Berlin"))[0], 0)  # short role words stay whole

    def test_career_switcher_in_uk(self):
        p = dict(PROFILE, target_roles=["UX Designer", "Product Designer"], seniority=["junior", "entry level"],
                 locations=["London", "UK", "Remote"], skills=["Figma"])
        s = scan.Scorer(p, [], TODAY)
        sc, why, _ = s.judge(job("1", "UX Designer", loc="London, UK", text="1+ years of experience with Figma."))
        self.assertGreater(sc, 0); self.assertIn("no level in title", why)  # plain title, the text says junior
        self.assertEqual(s.judge(job("2", "UX Designer", loc="London, UK", text="Own our design system."))[0], 0)
        for t in ("Graduate Scheme - Digital Design", "Product Design Graduate Scheme 2027", "UX Design Apprentice (Level 4)"):
            self.assertGreater(s.judge(job(t, t, loc="London"))[0], 0, t)
        for loc in ("United Kingdom", "England", "Manchester, England, United Kingdom"):
            self.assertGreater(s.judge(job(loc, "Junior UX Designer", loc=loc))[0], 0, loc)
        self.assertIn("US only", s.judge(job("3", "Junior UX Designer", loc="Remote - US only", remote=True))[1])
        self.assertGreater(s.judge(job("4", "Junior UX Designer", loc="Remote - UK only", remote=True))[0], 0)

    def test_spanish_postings(self):
        p = dict(PROFILE, target_roles=["Analista de datos"], seniority=["intern", "entry level"], locations=["Madrid", "España", "Remoto"],
                 skills=["SQL", "Python"])
        s = scan.Scorer(p, [], TODAY)
        sc, why, _ = s.judge(job("1", "Becario/a Analista de Datos", loc="Madrid, Spain", text="SQL y Python."))
        self.assertGreater(sc, 0); self.assertIn("role: Analista de datos", why)
        self.assertGreater(s.judge(job("2", "Prácticas Analista BI", loc="Barcelona, Spain"))[0], 0)  # role noun is "analista", not "datos"
        self.assertEqual(s.judge(job("3", "Becario Ingeniero de Datos", loc="Madrid"))[0], 0)  # "datos" alone is not the role
        self.assertIn("3+ years", s.judge(job("4", "Recién graduado Analista de datos", loc="Madrid", text="3 años de experiencia en SQL"))[1])
        self.assertGreater(s.judge(job("5", "Becario Analista de datos", loc="Teletrabajo"))[0], 0)
        for loc in ("Remote (United States)", "Remote - Americas", "Remote, US"):
            self.assertEqual(s.judge(job(loc, "Becario Analista de datos", loc=loc, remote=True))[0], 0, loc)
        us = scan.Scorer(dict(p, locations=["US", "Remote"]), [], TODAY)
        self.assertGreater(us.judge(job("6", "Becario Analista de datos", loc="Remote - Americas", remote=True))[0], 0)


class Run(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.data = pathlib.Path(self.tmp.name)
        self.cfg = {"data_dir": str(self.data)}
        (self.data / "applications.json").write_text(json.dumps([{"company": "Zed", "stage": "sent", "status": "waiting"}]), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def boards(self, calls):
        def fetch(src, slug):
            if slug == "acme":
                return [job("gh-acme-1", "Junior Software Engineer", text="Python, mentorship", posted="2026-11-03"),
                        job("gh-acme-2", "Intern, Finance", text="Excel only", posted="2026-01-01"),
                        job("gh-acme-3", "Senior Engineer")]
            if slug == "zed":
                return [job("ab-zed-1", "Junior Game Developer", text="Unity, C#", company="Zed", remote=True)]
            raise RuntimeError("boom")
        return fetch

    def test_same_job_twice_and_another_role(self):
        (self.data / "applications.json").write_text(json.dumps(
            [{"company": "Zed", "role": "Junior Software Engineer", "stage": "sent"}]), encoding="utf-8")

        def fetch(src, slug):
            if slug == "acme":
                return [job("gh-acme-1", "Junior Software Engineer (m/w/d)", text="Python", posted="2026-11-03", company="ACME GmbH"),
                        job("gh-acme-9", "Junior Software Engineer", text="Python, C#", posted="2026-11-03", company="Acme")]
            return [job("ab-zed-1", "Junior Software Engineer", text="Unity", company="Zed", remote=True),
                    job("ab-zed-2", "Junior Game Developer", text="Unity, C#", company="Zed", remote=True)]
        out, _, _ = scan.run(PROFILE, self.cfg, TODAY, fetch)
        new = {r["company"].split()[0].lower(): r for r in out["new"]}
        self.assertEqual(len(out["new"]), 2)  # the two Acme posts are one job
        self.assertEqual(new["zed"]["role"], "Junior Game Developer")
        self.assertIn("already applied there for Junior Software Engineer", new["zed"]["reason"])
        self.assertTrue(any("already tracked" in c["what"] for c in out["changed"]))

    def test_skill_aliases(self):
        s = scan.Scorer(dict(PROFILE, skills=["JavaScript", "Kubernetes"]), [], TODAY)
        _, why, _ = s.judge(job("1", "Junior Software Engineer", text="JS and k8s; some Java."))
        self.assertIn("skills: JavaScript, Kubernetes", why)
        _, why, _ = scan.Scorer(dict(PROFILE, skills=["Java"]), [], TODAY).judge(
            job("2", "Junior Software Engineer", text="JavaScript only."))
        self.assertNotIn("skills", why)
        go = scan.Scorer(dict(PROFILE, skills=["Go"]), [], TODAY)
        for text in ("Plan the go-live with us.", "Let's go! We ship weekly.", "Be ready to go."):
            self.assertNotIn("skills", go.judge(job("3", "Junior Software Engineer", text=text))[1], text)
        self.assertIn("skills: Go", go.judge(job("4", "Junior Software Engineer", text="Services in Go and Python."))[1])

    def test_german_postings(self):
        de = dict(PROFILE, locations=["Berlin, Germany"], applicant={"languages": ["English C1", "German B1"]})
        s = scan.Scorer(de, [], TODAY)
        # remote inside the country the profile lives in: kept, and the drop reason elsewhere names the place in full
        self.assertGreater(s.judge(job("1", "Junior Software Engineer", loc="Remote (Germany)"))[0], 0)
        self.assertGreater(s.judge(job("1b", "Junior Software Engineer", loc="Homeoffice, Deutschland"))[0], 0)
        self.assertEqual(s.judge(job("2", "Junior Software Engineer", loc="Remote (US)"))[0], 0)
        anywhere = scan.Scorer(dict(de, locations=["Remote", "Berlin, Germany"]), [], TODAY)
        self.assertEqual(anywhere.judge(job("2a", "Junior Software Engineer", loc="Remote (US)"))[1], "remote, US only")
        self.assertGreater(anywhere.judge(job("2c", "Junior Software Engineer", loc="Remote - Germany only"))[0], 0)
        self.assertGreater(s.judge(job("2b", "Junior Software Engineer", loc="Vollzeit"))[0], 0)  # a job type, not a place
        self.assertGreater(s.judge(job("2d", "Junior Software Engineer", loc="Berlin"))[0], 0)  # the city alone
        self.assertEqual(s.judge(job("2e", "Junior Software Engineer", loc="München, Germany"))[0], 0)  # same country, other city
        # the company's age is not a years requirement
        self.assertGreater(s.judge(job("3", "Junior Software Engineer", loc="Berlin", text="Wir sind seit 15 Jahren in der Branche."))[0], 0)
        self.assertEqual(s.judge(job("4", "Junior Software Engineer", loc="Berlin", text="Mindestens 5 Jahre Berufserfahrung."))[0], 0)
        # German asked above the profile's level: named in the reason, a point lower
        base, _, _ = s.judge(job("5", "Junior Software Engineer", loc="Berlin", text="Python."))
        score, why, _ = s.judge(job("6", "Junior Software Engineer", loc="Berlin", text="Python. Fließende Deutschkenntnisse in Wort und Schrift."))
        self.assertIn("asks German C1, you have B1", why)
        self.assertEqual(score, base - 1)
        self.assertNotIn("German", s.judge(job("7", "Junior Software Engineer", loc="Berlin", text="Python. Gute Deutschkenntnisse sind von Vorteil."))[1])
        self.assertNotIn("German", scan.Scorer(PROFILE, [], TODAY).judge(  # no languages in the profile: not judged
            job("8", "Junior Software Engineer", text="Verhandlungssicheres Deutsch."))[1])
        # German titles: Entwickler is a developer, team leads are out, gender endings are one job
        self.assertGreater(s.judge(job("9", "Junior Softwareentwickler (m/w/d)", loc="Berlin"))[0], 0)
        self.assertEqual(s.judge(job("10", "Teamleiter Softwareentwicklung", loc="Berlin"))[0], 0)
        self.assertEqual(scan.same("Acme GmbH", "Junior Entwickler:in"), scan.same("Acme", "Junior Entwickler*in"))
        self.assertEqual(scan.same("Acme", "Junior Entwickler:in"), scan.same("Acme", "Junior Entwickler"))

    def test_first_run_then_diff(self):
        out, state, errors = scan.run(PROFILE, self.cfg, TODAY, self.boards(None))
        self.assertEqual(errors, [])
        self.assertEqual([r["company"] for r in out["new"]], ["Acme"])
        self.assertEqual(out["new"][0]["score"], 5)
        self.assertTrue(any("already tracked (sent)" in c["what"] for c in out["changed"]))  # Zed is in applications.json
        self.assertEqual({d["role"] for d in out["dropped"]}, {"Intern, Finance", "Senior Engineer"})
        self.assertIn("Intern, Finance", [d["role"] for d in out["dropped"] if "no target role" in d["reason"]])
        self.assertEqual(out["sources"], ["greenhouse/acme", "ashby/zed"])
        self.assertIn("best: Acme (5/5)", out["summary"])
        self.assertEqual(state["gh-acme-1"]["src"], "greenhouse/acme")
        (self.data / "scan-state.json").write_text(json.dumps(state), encoding="utf-8")

        # second run: acme-1 gone from the board, acme-3 still senior (never reported again), zed board fails
        def fetch(src, slug):
            if slug == "acme":
                return [job("gh-acme-3", "Senior Engineer")]
            raise RuntimeError("boom")
        out2, state2, errors2 = scan.run(PROFILE, self.cfg, TODAY + datetime.timedelta(days=1), fetch)
        self.assertEqual(len(errors2), 1); self.assertIn("ashby/zed", errors2[0])
        self.assertEqual(out2["new"], []); self.assertEqual(out2["dropped"], [])
        self.assertEqual([c["company"] for c in out2["closed"]], ["Acme"])     # acme-1 gone
        self.assertIn("ab-zed-1", state2)                                        # failed board keeps its state
        self.assertEqual(state2["gh-acme-1"]["first"], TODAY.isoformat())       # old entries kept 60 days

    def test_unknown_board_type(self):
        out, state, errors = scan.run(dict(PROFILE, boards={"_": "comment", "indeed": ["x"]}), self.cfg, TODAY, self.boards(None))
        self.assertEqual(errors, ["unknown board type indeed"]); self.assertEqual(out["sources"], [])

    def test_scan_json_feeds_build(self):
        import build
        out, state, _ = scan.run(PROFILE, self.cfg, TODAY, self.boards(None))
        ex = pathlib.Path(__file__).parent / "example-data"
        for f in ex.iterdir():
            if f.name != "scan.json": (self.data / f.name).write_bytes(f.read_bytes())
        (self.data / "scan.json").write_text(json.dumps(out), encoding="utf-8")
        cfg = build.load_config(None, data_dir=str(self.data), out_dir=str(self.data / "out"))
        html = build.render_html(**build.build(cfg, TODAY))
        self.assertIn("5/5", html); self.assertIn("Junior Software Engineer", html)


class Parsers(unittest.TestCase):
    def test_source_parsers(self):
        calls = {}
        scan.get = lambda url: calls.setdefault(url, {
            "greenhouse": {"jobs": [{"id": 7, "title": "T", "location": {"name": "Berlin"}, "absolute_url": "u", "content": "<p>Hi &amp; bye</p>", "first_published": "2026-11-01T10:00:00-04:00"}]},
            "lever": [{"id": "a", "text": "T", "hostedUrl": "u", "createdAt": 1793836800000, "workplaceType": "remote", "descriptionPlain": "d", "categories": {"allLocations": ["Berlin", "Remote"]}}],
            "ashby": {"jobs": [{"id": "b", "title": "T", "location": "Berlin", "secondaryLocations": [{"location": "Remote"}], "isRemote": True, "jobUrl": "u", "descriptionHtml": "<b>d</b>", "publishedAt": "2026-11-01T00:00:00Z"},
                               {"id": "c", "title": "hidden", "isListed": False}]},
        }["greenhouse" if "greenhouse" in url else "lever" if "lever" in url else "ashby"])
        gh, lv, ab = list(scan.greenhouse("x")), list(scan.lever("x")), list(scan.ashby("x"))
        self.assertEqual((gh[0]["id"], gh[0]["location"], gh[0]["text"], gh[0]["posted"][:10]), ("gh-x-7", "Berlin", "Hi & bye", "2026-11-01"))
        self.assertEqual((lv[0]["remote"], lv[0]["location"], lv[0]["posted"]), (True, "Berlin, Remote", "2026-11-05"))
        self.assertEqual(len(ab), 1); self.assertEqual((ab[0]["remote"], ab[0]["location"], ab[0]["text"]), (True, "Berlin, Remote", "d"))

    def test_personio(self):
        from unittest import mock
        import io
        feed = (b'<?xml version="1.0"?><workzag-jobs><position><id>42</id><subcompany>Acme GmbH</subcompany><office>Berlin</office>'
                b'<additionalOffices><additionalOffice>Remote</additionalOffice></additionalOffices><name>Werkstudent Python</name>'
                b'<jobDescriptions><jobDescription><name>Tasks</name><value>&lt;p&gt;APIs&lt;/p&gt;</value></jobDescription></jobDescriptions>'
                b'<createdAt>2026-11-03T10:00:00+00:00</createdAt></position></workzag-jobs>')
        html404 = b"<!DOCTYPE html><html>Page Not Found</html>"
        urls = []
        def opener(pages):
            return lambda req, timeout=None: urls.append(getattr(req, "full_url", req)) or mock.MagicMock(__enter__=lambda s: io.BytesIO(pages.pop(0)))
        with mock.patch.object(scan.urllib.request, "urlopen", opener([html404, feed])):
            j = list(scan.personio("acme"))
        self.assertEqual((j[0]["id"], j[0]["company"], j[0]["location"], j[0]["remote"], j[0]["text"]),
                         ("ps-acme-42", "Acme GmbH", "Berlin, Remote", True, "Tasks: APIs"))
        self.assertEqual(j[0]["link"], "https://acme.jobs.personio.com/job/42")  # .de answered 404, .com had the board
        self.assertFalse(any("language" in u for u in urls))  # ?language=en empties most German descriptions
        with mock.patch.object(scan.urllib.request, "urlopen", opener([html404, html404])), self.assertRaises(ValueError):
            list(scan.personio("nope"))

    def test_more_parsers(self):
        pages = {
            "workable": {"jobs": [{"shortcode": "AB1", "title": " Dev ", "city": "Berlin", "country": "Germany", "telecommuting": True,
                                   "url": "u", "published_on": "2026-11-02", "description": "<p>py</p>"}]},
            "recruitee": {"offers": [{"id": 9, "title": "Dev", "company_name": "Acme", "location": "Remote", "remote": True,
                                      "published_at": "2026-11-03 10:00:00 UTC", "careers_url": "u", "description": "<p>a</p>", "requirements": "<li>b</li>"}]},
            "postings?": {"totalFound": 1, "content": [{"id": "77", "name": "Junior Software Engineer", "company": {"name": "Big"}, "releasedDate": "2026-11-04T00:00:00Z",
                                                       "location": {"fullLocation": "Paris, France", "remote": False}}]},
            "postings/77": {"jobAd": {"sections": {"jobDescription": {"title": "x", "text": "<p>build</p>"}, "qualifications": {"text": "python"}}}},
            "remotive": {"jobs": [{"id": 5, "title": "Dev", "company_name": "R", "candidate_required_location": "Europe", "publication_date": "2026-11-05T00:00:00", "url": "u", "description": "d"}]},
            "arbeitnow": {"data": [{"slug": "dev-1", "title": "Dev", "company_name": "A", "tags": ["Python"], "remote": True, "location": "Berlin", "created_at": 1793836800, "url": "u", "description": "d"},
                                   {"slug": "chef-1", "title": "Chef", "company_name": "B", "tags": ["Gastro"], "created_at": 1793836800, "url": "u"},
                                   {"slug": "be-2", "title": "Backend (Python)", "company_name": "C", "tags": ["Engineering"], "created_at": 1793836800, "url": "u"}]},
            "remoteok": [{"legal": "notice"}, {"id": "3", "position": "Dev", "company": "O", "location": "Worldwide", "date": "2026-11-06T00:00:00+00:00", "url": "u", "description": "d"}],
        }
        calls, real = [], scan.get
        def fake(url):
            calls.append(url)
            if "arbeitnow" in url and "page=1" not in url:
                return {"data": []}
            return next(v for k, v in pages.items() if k in url)
        scan.get = fake
        try:
            wk, rc, ra, an, ro = (list(scan.workable("acme")), list(scan.recruitee("acme")), list(scan.remotive("software-dev")),
                                  list(scan.arbeitnow("python")), list(scan.remoteok("python")))
            sr = list(scan.smartrecruiters("Big"))
            self.assertEqual((wk[0]["id"], wk[0]["title"], wk[0]["location"], wk[0]["remote"], wk[0]["text"]), ("wk-acme-AB1", "Dev", "Berlin, Germany", True, "py"))
            self.assertEqual((rc[0]["company"], rc[0]["remote"], rc[0]["text"], rc[0]["posted"][:10]), ("Acme", True, "a b", "2026-11-03"))
            self.assertEqual((ra[0]["id"], ra[0]["remote"], ra[0]["location"]), ("rm-5", True, "Europe"))
            self.assertEqual([j["id"] for j in an], ["an-dev-1", "an-be-2"]); self.assertEqual(an[0]["posted"], "2026-11-05")
            self.assertEqual([j["id"] for j in ro], ["ro-3"])  # legal notice row skipped
            self.assertTrue(callable(sr[0]["text"])); self.assertFalse(any("postings/77" in c for c in calls))  # detail is lazy
            self.assertEqual((sr[0]["company"], sr[0]["location"]), ("Big", "Paris, France"))
            sc = scan.Scorer(PROFILE, [], TODAY)
            sc.judge(sr[0])
            self.assertEqual(sr[0]["text"], "build python"); self.assertTrue(any("postings/77" in c for c in calls))
        finally:
            scan.get = real


if __name__ == "__main__":
    unittest.main()
