# -*- coding: utf-8 -*-
"""apply.py: the record, the approval gate and the form check. Run: python -I tracker/test_apply.py"""
import contextlib, io, json, pathlib, sys, tempfile, unittest

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import apply, build

AP = {"full_name": "Ada Lovelace", "email": "ada@example.com", "phone": "+44 7700 900123",
      "education": "University of London, BSc Mathematics, 2027 (expected)", "current_employer": "",
      "needs_sponsorship": "no", "links": ["https://github.com/ada", "linkedin.com/in/ada"], "salary": "40000 GBP"}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        (self.tmp / "data").mkdir()
        (self.tmp / "config.json").write_text(json.dumps({"data_dir": "data", "out_dir": "out"}), encoding="utf-8")
        (self.tmp / "profile.json").write_text(json.dumps({"quality": {"min_score": 3}, "applicant": AP}), encoding="utf-8")
        (self.tmp / "data" / "scan.json").write_text(json.dumps({"new": [
            {"company": "Acme", "role": "Junior Dev", "link": "https://x/1", "score": 4},
            {"company": "Globex", "role": "Intern", "link": "https://x/2", "score": 2},
            {"company": "Initech", "role": "Analyst", "link": "https://x/3", "score": 3}]}), encoding="utf-8")

    def run_(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            try:
                code = apply.main(["--config", str(self.tmp / "config.json"), *args])
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 2
                out.write(str(e.code))
        return code, out.getvalue()

    def rows(self):
        return json.loads((self.tmp / "data" / "applications.json").read_text(encoding="utf-8"))


class Record(Base):
    def test_todo_skips_low_scores_and_tracked(self):
        code, out = self.run_("todo")
        self.assertEqual([json.loads(l)["company"] for l in out.splitlines()], ["Acme", "Initech"])
        self.run_("add", "--company", "Acme", "--role", "Junior Dev", "--posting", "https://x/1", "--stage", "drafted")
        code, out = self.run_("todo", "--max", "5")
        self.assertEqual([json.loads(l)["company"] for l in out.splitlines()], ["Initech"])

    def test_sent_needs_check_then_approval(self):
        self.run_("add", "--company", "Acme", "--role", "Junior Dev", "--stage", "drafted")
        self.assertNotEqual(self.run_("set", "acme-junior-dev", "sent")[0], 0)
        self.assertNotEqual(self.run_("sent", "acme-junior-dev")[0], 0)
        self.assertNotEqual(self.run_("approve", "acme-junior-dev", "--quote", "yes")[0], 0)  # not checked yet
        form = self.tmp / "form.json"
        form.write_text(json.dumps({"Email": "ada@example.com", "Full name": "Ada Lovelace"}), encoding="utf-8")
        self.assertEqual(self.run_("check", str(form), "--id", "acme-junior-dev")[0], 0)
        self.assertTrue(self.rows()[0]["awaiting"])
        self.assertNotEqual(self.run_("sent", "acme-junior-dev")[0], 0)
        self.assertEqual(self.run_("approve", "acme-junior-dev", "--quote", "evet gönder")[0], 0)
        self.assertEqual(self.run_("sent", "acme-junior-dev")[0], 0)
        r = self.rows()[0]
        self.assertEqual((r["stage"], r["approval"]), ("sent", "evet gönder"))
        self.assertNotIn("awaiting", r)

    def test_failed_check_does_not_mark_awaiting(self):
        self.run_("add", "--company", "Acme", "--role", "Junior Dev")
        form = self.tmp / "form.json"
        form.write_text(json.dumps({"Email": "someone@else.com"}), encoding="utf-8")
        code, out = self.run_("check", str(form), "--id", "acme-junior-dev")
        self.assertEqual(code, 1)
        self.assertIn("FAIL Email", out)
        self.assertNotIn("awaiting", self.rows()[0])

    def test_failed_recheck_takes_the_approval_back(self):
        self.run_("add", "--company", "Acme", "--role", "Junior Dev")
        good, bad = self.tmp / "good.json", self.tmp / "bad.json"
        good.write_text(json.dumps({"Email": "ada@example.com"}), encoding="utf-8")
        bad.write_text(json.dumps({"Email": "someone@else.com"}), encoding="utf-8")
        self.run_("check", str(good), "--id", "acme-junior-dev")
        self.run_("approve", "acme-junior-dev", "--quote", "evet gönder")
        self.assertEqual(self.run_("check", str(bad), "--id", "acme-junior-dev")[0], 1)
        code, out = self.run_("sent", "acme-junior-dev")
        self.assertNotEqual(code, 0)
        self.assertNotEqual(self.rows()[0]["stage"], "sent")

    def test_add_cannot_move_a_sent_record_back(self):
        self.run_("add", "--company", "Acme", "--role", "Junior Dev")
        form = self.tmp / "form.json"
        form.write_text(json.dumps({"Email": "ada@example.com"}), encoding="utf-8")
        self.run_("check", str(form), "--id", "acme-junior-dev")
        self.run_("approve", "acme-junior-dev", "--quote", "evet gönder")
        self.run_("sent", "acme-junior-dev")
        code, out = self.run_("add", "--company", "Acme", "--role", "Junior Dev")
        self.assertNotEqual(code, 0)
        self.assertEqual(self.rows()[0]["stage"], "sent")

    def test_linkedin_link_with_tracking_text_still_matches(self):
        self.assertEqual(apply.url("https://www.linkedin.com/in/ada/?trk=public"), "linkedin.com/in/ada")

    def test_board_shows_drafted_and_waiting(self):
        self.run_("add", "--company", "Acme", "--role", "Junior Dev", "--stage", "drafted")
        form = self.tmp / "form.json"
        form.write_text(json.dumps({"Email": "ada@example.com"}), encoding="utf-8")
        self.run_("check", str(form), "--id", "acme-junior-dev")
        build.build(build.load_config(str(self.tmp / "config.json")))
        page = (self.tmp / "out" / "index.html").read_text(encoding="utf-8")
        self.assertIn('class="col drafted"', page)
        self.assertIn("waiting for your approval before it is sent: Acme", page)


class Stats(Base):
    def test_funnel_quiet_and_late(self):
        rows = [dict(id="a", company="A", stage="sent", sent_on="2026-10-01"),
                dict(id="b", company="B", stage="sent", sent_on="2026-11-18"),
                dict(id="c", company="C", stage="process", sent_on="2026-10-05"),
                dict(id="d", company="D", stage="closed", sent_on="2026-10-02"),
                dict(id="e", company="E", stage="watching", deadline="2026-11-01"),
                dict(id="f", company="F", stage="watching", deadline="soon")]
        (self.tmp / "data" / "applications.json").write_text(json.dumps(rows), encoding="utf-8")
        code, out = self.run_("--today", "2026-11-20", "stats")
        self.assertEqual(code, 0)
        self.assertIn("sent 4, answered with an interview or offer 1 (25%)", out)
        self.assertIn("quiet 50 days: A", out)
        self.assertNotIn("B (b)", out)  # sent two days ago
        self.assertIn("deadline passed 2026-11-01: E", out)
        self.assertNotIn("F (f)", out)

    def test_empty_book(self):
        code, out = self.run_("stats")
        self.assertEqual(code, 0)
        self.assertIn("0 applications", out)


class Form(unittest.TestCase):
    def bad(self, form):
        return [w for _, w in apply.check_form(form, AP)]

    def test_clean_form_passes(self):
        self.assertEqual(self.bad({"First name": "Ada", "Last name": "Lovelace", "Email": "ADA@example.com",
                                   "Phone": "07700 900123", "Expected graduation": "June 2027", "Current company": "",
                                   "Will you require visa sponsorship?": "No", "GitHub": "github.com/ada/",
                                   "Company name of last employer": "Analytical Engines Ltd", "Salary expectation": "40,000"}), [])

    def test_wrong_facts_fail(self):
        bad = self.bad({"Name": "Grace Hopper", "Email": "ada@gmail.com", "Phone": "+44 7700 900999",
                        "Graduation year": "2026", "Current employer": "Barko", "Visa sponsorship needed?": "Yes",
                        "LinkedIn": "linkedin.com/in/someone", "Salary": "55000"})
        self.assertEqual(len(bad), 8, bad)

    def test_old_profile_without_employer_key(self):
        old = {k: v for k, v in AP.items() if k != "current_employer"}
        self.assertEqual(apply.check_form({"Current employer": "Barko"}, old), [])
        self.assertEqual(apply.check_form("I am currently working at Barko.", old), [])

    def test_salary_forms(self):
        gbp = dict(AP, salary="£32,000")
        for same in ("£32k", "32000", "£30,000-£34,000", "32.000 €"):
            self.assertEqual(apply.check_form({"Salary expectation": same}, gbp), [], same)
        for other in ("£45k", "£20,000 - £25,000"):
            self.assertTrue(apply.check_form({"Salary expectation": other}, gbp), other)

    def test_german_and_permit_labels(self):
        bad = self.bad({"Vorname": "Moritz", "Benötigen Sie eine Arbeitserlaubnis?": "Ja",
                        "Are you authorized to work in Germany?": "No", "Gehaltsvorstellung": "45.000 €"})
        self.assertEqual(len(bad), 4, bad)
        self.assertEqual(self.bad({"Vorname": "Ada", "Haben Sie eine Arbeitserlaubnis?": "Ja",
                                   "Are you authorized to work in Germany?": "Yes", "Gehaltsvorstellung": "40.000"}), [])
        # German phone, graduation, employer and link labels are checked too
        self.assertTrue(self.bad({"Mobilnummer": "+49 151 1234567"}))
        self.assertTrue(self.bad({"Abschlussjahr": "2026"}))
        self.assertTrue(self.bad({"Aktueller Arbeitgeber": "Barko GmbH"}))
        self.assertTrue(self.bad({"XING-Profil": "https://www.xing.com/profile/Someone_Else"}))
        self.assertEqual(self.bad({"Mobilnummer": "+44 7700 900123", "Abschlussjahr": "2027"}), [])
        self.assertEqual(self.bad({"Mobilität": "Ja, bundesweit"}), [])  # not a phone field

    def test_placeholder_left(self):
        self.assertTrue(self.bad({"Why us?": "I cut build time by [number?] percent"}))

    def test_plain_text(self):
        self.assertTrue(self.bad("I am currently working at Barko as an intern."))
        self.assertTrue(self.bad("I will graduate in 2026."))
        self.assertTrue(self.bad("Reach me at ada@other.org"))
        self.assertEqual(self.bad("I will graduate in 2027 and can start in July."), [])


if __name__ == "__main__":
    unittest.main()
