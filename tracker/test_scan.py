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
        s2, why2, _ = self.s.judge(job("2", "Intern Game Tester (QA)", text="Unpaid position.", posted="2026-06-01"))
        self.assertEqual(s2, 1)  # 1 + role 2 - weak 1 - old 1 → clamped to 1
        self.assertIn("role: Game Developer", why2); self.assertIn("-Unpaid", why2); self.assertIn("days ago", why2)

    def test_role_words_must_match_the_title(self):
        s = scan.Scorer(dict(PROFILE, target_roles=["Product Designer"], seniority=[]), [], TODAY)
        self.assertIn("role: Product Designer", s.judge(job("1", "Junior Product Designer"))[1])
        self.assertIn("role word: designer", s.judge(job("2", "UX Designer"))[1])
        self.assertEqual(s.judge(job("3", "Product Support Specialist")), (0, "title: no target role", {}))

    def test_rejection_feedback(self):
        apps = [{"company": "Acme", "stage": "closed", "status": "rejected after interview"}]
        s = scan.Scorer(PROFILE, apps, TODAY)
        self.assertIn("rejected you before", s.judge(job("1", "Junior Software Engineer", text="Python"))[1])

    def test_default_exclude_and_seniority_synonyms(self):
        p = dict(PROFILE, exclude=None, seniority=["entry level"])
        s = scan.Scorer(p, [], TODAY)
        self.assertGreater(s.judge(job("1", "New Grad Software Engineer"))[0], 0)
        self.assertEqual(s.judge(job("2", "Staff Engineer, New Grad Program"))[0], 0)


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


if __name__ == "__main__":
    unittest.main()
