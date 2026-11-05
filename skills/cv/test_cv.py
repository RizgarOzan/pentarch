# -*- coding: utf-8 -*-
"""Tests for cv.py. No files, no network.  python -I skills/cv/test_cv.py"""
import io, pathlib, sys, unittest
from contextlib import redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import cv

GOOD = """# A. Person
+1 555 000 0000 | a@mail.com | linkedin.com/in/aperson | github.com/aperson

## EDUCATION
**Some University**                                   City, Country
*B.Sc. in Computer Science*                           Sept. 2021 -- June 2025

## EXPERIENCE
**Software Engineer**                                 Mar. 2025 -- Present
*Acme*                                                City, Country
- Cut API latency 80%, from 10 s to 2 s, by caching the 3 hottest queries
- Shipped 4 features to 12,000 users with a 2-person team
- Wrote 140 tests that caught 9 regressions before release

**Intern**                                            June 2024 -- Aug. 2024
*Beta Ltd*                                            City, Country
- Built a CSV import that replaced 6 hours of weekly manual entry
- Reduced build time 30% by splitting 2 CI jobs
- Documented 15 endpoints used by 3 partner teams

## PROJECTS
**Tracker** | *Python, SQLite*                        Jan. 2025 -- Present
- Scan 5 job boards nightly and score 200 postings in 4 seconds
- Serve 1 static HTML page with 0 dependencies
- Keep 19 tests green on every push

## TECHNICAL SKILLS
**Languages**: Python, C#, SQL
**Tools**: Git, Docker
"""

JD = """We are hiring a Backend Engineer. Requirements: Python, PostgreSQL, Docker, Kubernetes.
Preferred: experience with Kafka, Terraform and gRPC. You will write Python services and run them on Kubernetes."""


def levels(rows):
    return [l for l, _ in rows]


def msgs(rows, level=None):
    return [m for l, m in rows if level is None or l == level]


class Check(unittest.TestCase):
    def test_good_passes(self):
        rows = cv.check_text(GOOD)
        self.assertNotIn("FAIL", levels(rows), rows)
        self.assertNotIn("WARN", levels(rows), rows)

    def test_template_itself_fails_only_on_placeholders(self):
        rows = cv.check_text(cv.TEMPLATE)
        self.assertIn("FAIL", levels(rows))
        self.assertFalse([m for m in msgs(rows, "FAIL") if "heading" in m or "email" in m], rows)

    def test_pronoun_and_duty_fail(self):
        bad = GOOD.replace("- Cut API latency 80%", "- I was responsible for API latency 80%")
        fails = msgs(cv.check_text(bad), "FAIL")
        self.assertTrue(any("pronoun" in m for m in fails), fails)
        self.assertTrue(any("responsible for" in m for m in fails), fails)

    def test_passive_weak_tense_repeat_warn(self):
        bad = GOOD.replace("- Wrote 140 tests", "- Assisted with 140 tests").replace(
            "- Built a CSV import", "- Build a CSV import").replace(
            "- Documented 15 endpoints", "- 15 endpoints were documented by me, 3 partner teams").replace(
            "- Reduced build time 30%", "- Shipped build time 30% faster")
        rows = cv.check_text(bad)
        w = msgs(rows, "WARN")
        self.assertTrue(any("starts with 'assisted'" in m for m in w), w)
        self.assertTrue(any("not past tense" in m for m in w), w)
        self.assertTrue(any("passive voice" in m for m in w), w)
        self.assertTrue(any("verb 'shipped' opens 2" in m for m in w), w)
        self.assertTrue(any("pronoun" in m for m in msgs(rows, "FAIL")))

    def test_numbers(self):
        bad = GOOD.replace("- Cut API latency 80%, from 10 s to 2 s, by caching the 3 hottest queries", "- Cut API latency a lot")
        self.assertTrue(any("first bullet" in m for m in msgs(cv.check_text(bad), "FAIL")))
        bad = GOOD.replace("- Shipped 4 features to 12,000 users with a 2-person team", "- Shipped many features")
        rows = cv.check_text(bad)
        self.assertNotIn("FAIL", levels(rows))
        self.assertTrue(any("no number" in m for m in msgs(rows, "WARN")))

    def test_headings_and_order(self):
        bad = GOOD.replace("## EXPERIENCE", "## My Career Path")
        self.assertTrue(any("My Career Path" in m for m in msgs(cv.check_text(bad), "FAIL")))
        no_email = GOOD.replace("a@mail.com", "mail on request")
        self.assertTrue(any("email" in m for m in msgs(cv.check_text(no_email), "FAIL")))
        older_first = GOOD.replace("Mar. 2025 -- Present", "June 2023 -- Aug. 2023")
        self.assertTrue(any("newer than" in m for m in msgs(cv.check_text(older_first), "WARN")))

    def test_bullet_count_date_first_table(self):
        many = GOOD.replace("- Keep 19 tests green on every push", "- Keep 19 tests green on every push\n- Ran 2 demos\n- Logged 3 bugs\n- Fixed 4 bugs")
        self.assertTrue(any("6 bullets" in m for m in msgs(cv.check_text(many), "WARN")))
        dated = GOOD.replace("**Intern**                                            June 2024 -- Aug. 2024", "June 2024 -- Aug. 2024 **Intern**")
        self.assertTrue(any("starts with a date" in m for m in msgs(cv.check_text(dated), "WARN")))
        table = GOOD + "\n| a | b |\n|---|---|\n"
        self.assertTrue(any("table" in m for m in msgs(cv.check_text(table), "FAIL")))
        self.assertEqual(cv.check_text("  \n"), [("FAIL", "empty file")])

    def test_skills_section(self):
        bad = GOOD.replace("**Tools**: Git, Docker", "**Tools**: Git, Docker, Microsoft Word\n**Other**: team player, intermediate Java")
        w = msgs(cv.check_text(bad), "WARN")
        self.assertTrue(any("obvious tool" in m for m in w), w)
        self.assertTrue(any("soft skill" in m for m in w), w)
        self.assertTrue(any("skill-level label" in m for m in w), w)

    def test_jd_keywords(self):
        kws = cv.jd_keywords(JD)
        for k in ("python", "kubernetes", "docker", "kafka", "postgresql"):
            self.assertIn(k, kws, kws)
        self.assertNotIn("requirements", kws)
        self.assertLess(kws.index("kafka"), kws.index("docker"))  # preferred terms rank above required ones
        rows = cv.check_text(GOOD, jd=JD)
        kw = [m for m in msgs(rows) if m.startswith("posting keywords")]
        self.assertEqual(len(kw), 1, rows)
        self.assertIn("missing: ", kw[0])
        self.assertIn("kubernetes", kw[0])

    def test_turkish_skips_english_verb_rules(self):
        tr = GOOD.replace("- Built a CSV import", "- 6 saatlik elle girişi kaldıran bir CSV aktarımı yazdım")
        self.assertTrue([m for m in msgs(cv.check_text(tr), "WARN") if "past tense" in m])
        rows = cv.check_text(tr, lang="tr")
        self.assertFalse([m for m in msgs(rows, "WARN") if "past tense" in m], rows)

    def test_main_exit_codes(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "cv.md"; p.write_text(GOOD, encoding="utf-8")
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(cv.main(["check", str(p)]), 0)
            self.assertIn("0 FAIL", out.getvalue())
            p.write_text(GOOD.replace("- Cut API", "- I cut API"), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cv.main(["check", str(p)]), 1)
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(cv.main(["template"]), 0)
            self.assertTrue(out.getvalue().startswith("# FULL NAME"))


if __name__ == "__main__":
    unittest.main()
