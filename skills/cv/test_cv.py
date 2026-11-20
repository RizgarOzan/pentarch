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

    def test_template_structure_is_clean(self):
        rows = cv.check_text(cv.TEMPLATE)
        self.assertNotIn("FAIL", levels(rows), rows)
        self.assertTrue(any("no number" in m for m in msgs(rows, "WARN")))

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
        rows = cv.check_text(bad)  # a missing number warns; a forced one gets invented
        self.assertNotIn("FAIL", levels(rows))
        self.assertTrue(any("never invent" in m for m in msgs(rows, "WARN")))
        bad = GOOD.replace("- Shipped 4 features to 12,000 users with a 2-person team", "- Shipped many features")
        rows = cv.check_text(bad)
        self.assertNotIn("FAIL", levels(rows))
        self.assertTrue(any("no number" in m for m in msgs(rows, "WARN")))

    def test_placeholder_ai_tone_profile(self):
        left = GOOD.replace("- Keep 19 tests green on every push", "- Cut build time by [number?] with caching")
        self.assertTrue(any("placeholder" in m for m in msgs(cv.check_text(left), "FAIL")))
        tone = GOOD.replace("- Keep 19 tests green on every push", "- Spearheaded 19 tests — seamless pushes")
        w = msgs(cv.check_text(tone), "WARN")
        self.assertTrue(any("spearheaded" in m.lower() for m in w), w)
        self.assertTrue(any("em dash" in m for m in w), w)
        short = GOOD.replace("## EDUCATION", "## PROFILE\nJunior backend developer, Berlin or remote, from March 2026\n\n## EDUCATION")
        self.assertFalse([m for m in msgs(cv.check_text(short)) if "PROFILE" in m])
        long_ = short.replace("from March 2026", "from March 2026\nLine 2\nLine 3")
        self.assertTrue([m for m in msgs(cv.check_text(long_), "WARN") if "PROFILE" in m])

    def test_headings_and_order(self):
        bad = GOOD.replace("## EXPERIENCE", "## My Career Path")
        self.assertTrue(any("My Career Path" in m for m in msgs(cv.check_text(bad), "FAIL")))
        teaching = GOOD.replace("## EXPERIENCE", "## Teaching Experience")  # a career changer's section still parses
        self.assertFalse(any("heading" in m for m in msgs(cv.check_text(teaching), "FAIL")))
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
        eeo = JD + "\nAcme is an Equal Opportunity Employer. We hire Regardless of Race, Religion, Sexual Orientation or Veteran Status.\n"
        for k in ("religion", "veteran", "opportunity"):
            self.assertNotIn(k, cv.jd_keywords(eeo))
        self.assertLess(kws.index("docker"), kws.index("kafka"))  # must-haves rank above nice-to-haves
        rows = cv.check_text(GOOD, jd=JD)
        kw = [m for m in msgs(rows) if m.startswith("posting keywords")]
        self.assertEqual(len(kw), 1, rows)
        self.assertIn("missing: ", kw[0])
        self.assertIn("kubernetes", kw[0])

    def test_keyword_is_a_whole_word(self):
        low = "built a javascript app on k8s with postgres; good at node.js."
        self.assertFalse(cv.has_word("java", low))  # not inside "javascript"
        self.assertFalse(cv.has_word("go", low))  # not inside "good"
        for k in ("javascript", "kubernetes", "postgresql", "node.js"):
            self.assertTrue(cv.has_word(k, low), k)
        self.assertTrue(cv.has_word("c#", "c#, python."))
        self.assertFalse(cv.has_word("c", "c#, python."))
        self.assertFalse(cv.has_word("go", "plan the go-live."))

    def test_german_cv(self):
        de = GOOD.replace("## EDUCATION", "## Bildungsweg").replace("## EXPERIENCE", "## Beruflicher Werdegang")
        heads = [m for lvl, m in cv.check_text(de) if lvl == "FAIL" and "heading" in m]
        self.assertEqual(heads, [])
        self.assertIsNotNone(cv.DATE_RX.search("**Entwickler**   seit 03/2024"))
        m = cv.DATE_RX.search("**Werkstudent**   10.2023 – aktuell")
        self.assertIsNotNone(m)
        self.assertEqual(cv.date_key(m), (9999, 13))
        self.assertEqual(cv.date_key(cv.DATE_RX.search("09/2021 – 06.2023")), (2023, 6))
        jd = ("Du betreust unsere Kubernetes-Infrastruktur.\nErfahrung mit Kubernetes-Clustern und Go.\n"
              "Let's go: wir freuen uns auf dich.")
        keys = cv.jd_keywords(jd, "de")
        self.assertIn("kubernetes", keys)
        self.assertIn("go", keys)
        self.assertNotIn("go", cv.jd_keywords("Let's go, we ship weekly.\nWe go fast.", "en"))

    def test_turkish_skips_english_verb_rules(self):
        tr = GOOD.replace("- Built a CSV import", "- 6 saatlik elle girişi kaldıran bir CSV aktarımı yazdım")
        self.assertTrue([m for m in msgs(cv.check_text(tr), "WARN") if "past tense" in m])
        rows = cv.check_text(tr, lang="tr")
        self.assertFalse([m for m in msgs(rows, "WARN") if "past tense" in m], rows)

    def test_cut_is_not_a_tense_mix(self):
        present = GOOD.replace("- Shipped 4 features", "- Ship 4 features").replace("- Wrote 140 tests", "- Write 140 tests")
        self.assertFalse([m for m in msgs(cv.check_text(present), "WARN") if "mixes" in m])
        mixed = present.replace("- Ship 4 features", "- Shipped 4 features")
        self.assertTrue([m for m in msgs(cv.check_text(mixed), "WARN") if "mixes" in m])

    def test_german(self):
        de = (GOOD.replace("## EDUCATION", "## AUSBILDUNG").replace("## EXPERIENCE", "## BERUFSERFAHRUNG")
              .replace("## PROJECTS", "## PROJEKTE").replace("## TECHNICAL SKILLS", "## KENNTNISSE")
              .replace("- Built a CSV import", "- Ich baute einen CSV-Import"))
        rows = cv.check_text(de, lang="de")
        self.assertFalse([m for m in msgs(rows, "FAIL") if "heading" in m], rows)
        self.assertTrue([m for m in msgs(rows, "FAIL") if "pronoun (Ich)" in m], rows)
        self.assertFalse([m for m in msgs(rows, "WARN") if "past tense" in m or "no Experience" in m], rows)
        jd = ("Werkstudent (m/w/d) Softwareentwicklung\nDeine Aufgaben: Du entwickelst Services mit Python und Docker.\n"
              "Dein Profil: Gute Kenntnisse in Python, Docker und SQL. Erste Erfahrung mit Kubernetes.\n"
              "Was wir bieten: Flexible Arbeitszeiten, JobRad, Urban Sports Club, 30 Tage Urlaub.\n")
        kws = cv.jd_keywords(jd, "de")
        for k in ("python", "docker"):
            self.assertIn(k, kws, kws)
        for k in ("aufgaben", "profil", "kenntnisse", "flexible", "jobrad", "urban", "deine"):
            self.assertNotIn(k, kws, kws)

    def test_spanish(self):
        es = (GOOD.replace("## EDUCATION", "## FORMACIÓN").replace("## EXPERIENCE", "## EXPERIENCIA PROFESIONAL")
              .replace("## PROJECTS", "## PROYECTOS").replace("## TECHNICAL SKILLS", "## HABILIDADES")
              .replace("Sept. 2021 -- June 2025", "sept. 2021 - jun. 2025").replace("Mar. 2025 -- Present", "ene. 2025 - actualidad")
              .replace("June 2024 -- Aug. 2024", "abr. 2024 - dic. 2024").replace("**Tools**: Git, Docker", "**Herramientas**: Excel, Power BI")
              .replace("- Built a CSV import", "- Yo construí una importación CSV"))
        rows = cv.check_text(es + "\nFecha de nacimiento: 01/01/2000\n", lang="es")
        self.assertFalse([m for m in msgs(rows, "FAIL") if "heading" in m], rows)
        self.assertFalse([m for m in msgs(rows, "WARN") if "date" in m and "birth" not in m or "no Experience" in m or "past tense" in m], rows)
        self.assertFalse([m for m in msgs(rows, "WARN") if "obvious tool" in m], rows)  # Excel is a data skill
        self.assertTrue([m for m in msgs(rows, "FAIL") if "pronoun (Yo)" in m], rows)
        self.assertTrue([m for m in msgs(rows, "WARN") if "birth date" in m], rows)
        self.assertEqual(cv.date_key(cv.DATE_RX.search("abr. 2024 - dic. 2024")), (2024, 12))

    def test_uk_cv(self):
        uk = (GOOD.replace("## EXPERIENCE", "## EMPLOYMENT HISTORY").replace("## TECHNICAL SKILLS", "## KEY SKILLS")
              .replace(" -- ", " to "))
        rows = cv.check_text(uk + "\n## QUALIFICATIONS\n\n**Google UX Design Certificate** 2025\n")
        self.assertFalse([m for m in msgs(rows, "FAIL") if "heading" in m], rows)
        self.assertFalse([m for m in msgs(rows, "WARN") if "no Experience" in m or "date" in m], rows)
        self.assertFalse([m for m in msgs(cv.check_text(GOOD.replace("github.com/", "janesmith.co.uk/")), "WARN") if "portfolio link" in m])
        case = GOOD.replace("## PROJECTS\n\n", "## PROJECTS\n\n**Booking redesign**\n- Reframed booking around parents on mobile after interviews\n", 1)
        self.assertFalse([m for m in msgs(cv.check_text(case), "FAIL") if "no number" in m])
        kws = cv.jd_keywords("You will work with Product Managers and engineers. Report to the Head of Design. "
                             "Managers and engineers rely on you; the Head reviews it.")
        for k in ("head", "managers", "engineers"):
            self.assertNotIn(k, kws, kws)

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
