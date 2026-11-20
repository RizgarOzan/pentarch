# -*- coding: utf-8 -*-
"""Tests for interview.py. Temp dir, no network.  python -I skills/interview/test_interview.py"""
import contextlib, io, json, pathlib, sys, tempfile, unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import interview


class Bank(unittest.TestCase):
    def setUp(self):
        self.f = str(pathlib.Path(tempfile.mkdtemp()) / "stories.json")

    def run_(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = interview.main(["--file", self.f, *args])
        return code, out.getvalue()

    def add(self, title, tags, **kw):
        d = dict(situation="Checkout was slow.", action="I profiled it and cached the cart query.",
                 result="Cut load time from 4s to 1s.", reflection="I would add a benchmark first.")
        d.update(kw)
        return self.run_("add", "--title", title, "--tags", tags, *sum((["--" + k, v] for k, v in d.items()), []))

    def test_add_replaces_same_title_and_lists_gaps(self):
        self.add("Cart speed", "technical")
        self.add("cart speed", "technical,impact")
        self.assertEqual(len(interview.load(self.f)), 1)
        _, out = self.run_("list")
        gaps = out.split("no story yet for:")[1]
        self.assertNotIn("technical", gaps)
        self.assertNotIn("impact", gaps)
        self.assertIn("conflict", gaps)

    def test_match_by_theme_and_by_nothing(self):
        self.add("Cart speed", "technical")
        self.add("Team fight", "conflict", situation="Two devs disagreed on the schema.",
                 action="I set up a call and we compared both.", result="Agreed in 1 day, shipped in 2 weeks.")
        _, out = self.run_("match", "Tell me about a time you had a disagreement with a teammate")
        self.assertTrue(out.startswith("Team fight"))
        code, out = self.run_("match", "What is your favourite colour")
        self.assertEqual(code, 1)
        self.assertIn("ask the owner", out)

    def test_check_flags_without_inventing(self):
        self.add("Vague", "impact", result="It went well.", action="We did a lot together.", reflection="")
        _, out = self.run_("check")
        self.assertIn("no number", out)
        self.assertIn("we/our only", out)
        self.assertIn("no reflection", out)
        self.assertEqual(interview.load(self.f)[0]["result"], "It went well.")  # untouched

    def test_clean_story_passes_and_long_one_is_flagged(self):
        self.add("Good", "impact")
        self.assertIn("ok", self.run_("check", "Good")[1])
        self.add("Long", "impact", situation="word " * 230)
        self.assertIn("over 90 seconds", self.run_("check", "Long")[1])


if __name__ == "__main__":
    unittest.main()
