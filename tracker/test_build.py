# -*- coding: utf-8 -*-
"""Builds the example data on several days, in both languages, with and without gh, and checks the output.
Run: python -m pytest tracker -q   (or: python tracker/test_build.py). Everything is written to a temp folder."""
import datetime, html.parser, pathlib, re, sys, tempfile, unittest
from unittest import mock

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
import build

# learning day before the plan, learning day inside it, practice days, a rest day, learning day after the plan, far future
DAYS = ["2026-10-14", "2026-11-04", "2026-11-05", "2026-11-07", "2026-11-08", "2026-12-16", "2027-03-01"]
GH = ({"merged": 5, "open": 3, "important": 2}, {"merged": None, "open": None, "important": None})
VOID = ("meta", "br", "input", "img", "link", "hr")

class P(html.parser.HTMLParser):
    def __init__(s): super().__init__(); s.ids, s.hrefs, s.stack, s.err, s.external = [], [], [], [], []
    def handle_starttag(s, t, a):
        a = dict(a)
        if "id" in a: s.ids.append(a["id"])
        if t == "a": s.hrefs.append(a.get("href", ""))
        if (t == "link" and re.match(r"https?:|//", a.get("href") or "")) or (t == "script" and a.get("src")): s.external.append(t)
        if t not in VOID: s.stack.append(t)
    def handle_endtag(s, t):
        if not s.stack or s.stack[-1] != t: s.err.append(f"unexpected </{t}>, open: {s.stack[-3:]}")
        else: s.stack.pop()

def problems(out):
    h = (out / "index.html").read_text(encoding="utf-8"); md = (out / "README.md").read_text(encoding="utf-8")
    p = P(); p.feed(h)
    bad = p.err[:3] + ([f"unclosed tags: {p.stack}"] if p.stack else []) + ([f"external resources: {p.external}"] if p.external else [])
    dup = {i for i in p.ids if p.ids.count(i) > 1}
    if dup: bad.append(f"duplicate ids: {dup}")
    for href in p.hrefs:
        if href.startswith("#") and href[1:] not in p.ids: bad.append(f"broken nav link {href}")
        elif href and not re.match(r"https?://|#", href) and not (out / href).exists(): bad.append(f"missing file: {href}")
    text = re.sub(r"<[^>]+>", " ", h) + md
    bad += [f"output has {x}" for x in (r"\bNone\b", r"\bnan\b", r"\{esc\(", r"\{link\(") if re.search(x, text)]
    return bad, p.ids

class TestBuild(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.out = pathlib.Path(self.tmp.name) / "out"
    def tearDown(self): self.tmp.cleanup()

    def cfg(self, **over):
        cfg = build.load_config(HERE / "config.example.json")
        cfg.update({"out_dir": self.out, "github_user": "someone", **over})
        return cfg

    def test_days_langs_gh(self):
        for lang in ("en", "tr"):
            for gh in GH:
                for day in DAYS:
                    with self.subTest(lang=lang, gh=gh["merged"], day=day), mock.patch.object(build, "gh_counts", lambda *a, gh=gh: gh):
                        build.build(self.cfg(lang=lang), datetime.date.fromisoformat(day))
                        bad, ids = problems(self.out)
                        self.assertEqual(bad, [])
                        for i in ("today", "applications", "scan", "learning", "oss", "other"): self.assertIn(i, ids)

    def test_rule_notes(self):
        with mock.patch.object(build, "gh_counts", lambda *a: GH[0]):
            ctx = build.build(self.cfg(), datetime.date(2026, 11, 5))
        notes = " | ".join(ctx["notlar"])
        for x in ("Northwind Analytics: deadline passed", "Not checked for 10+ days: Contoso Games", "Overdue task (8 days)",
                  "Finished? Week 1", "Open source:"):
            self.assertIn(x, notes)
        self.assertEqual(ctx["odak"]["tip"], "algorithms")  # Thursday is a practice day
        self.assertFalse(any(t == "event" and "Summit" in n for t, n, k, u in ctx["bugun"]))  # same link as a task -> task only

    def test_today_by_rhythm(self):
        with mock.patch.object(build, "gh_counts", lambda *a: GH[1]):
            self.assertEqual(build.build(self.cfg(), datetime.date(2026, 11, 4))["odak"]["baslik"], "Intro to Statistics")
            self.assertEqual(build.build(self.cfg(), datetime.date(2026, 11, 8))["odak"]["baslik"], "Rest day")
            self.assertIn("Rust", build.build(self.cfg(), datetime.date(2026, 12, 16))["odak"]["baslik"])  # plan over -> later list

    def test_gh_skipped_without_user_or_cli(self):
        with mock.patch.object(build.subprocess, "run", side_effect=AssertionError("gh must not run")):
            self.assertEqual(build.gh_counts("", ["a/b"]), {"merged": None, "open": None, "important": None})
            with mock.patch.object(build.shutil, "which", return_value=None):
                self.assertEqual(build.gh_counts("someone", []), {"merged": None, "open": None, "important": None})
            ctx = build.build(self.cfg(github_user="", backlog=""), datetime.date(2026, 11, 5))
        bad, ids = problems(self.out)
        self.assertEqual(bad, []); self.assertNotIn("oss", ids); self.assertFalse(any("gh" in n for n in ctx["notlar"]))

    def test_empty_data_dir(self):
        empty = pathlib.Path(self.tmp.name) / "empty"; empty.mkdir()
        for lang in ("en", "tr"):
            build.build(build.load_config(data_dir=empty, out_dir=self.out, lang=lang), datetime.date(2026, 11, 5))
            bad, ids = problems(self.out)
            self.assertEqual(bad, []); self.assertNotIn("scan", ids)

    def test_config_paths_relative_to_file(self):
        root = pathlib.Path(self.tmp.name)
        (root / "config.json").write_text('{"data_dir": "mine", "lang": "tr"}', encoding="utf-8")
        cfg = build.load_config(root / "config.json", out_dir=str(self.out))
        self.assertEqual(cfg["data_dir"], (root / "mine").resolve())
        self.assertEqual(cfg["out_dir"], self.out.resolve())
        self.assertEqual(cfg["lang"], "tr")

    def test_cli(self):
        with mock.patch.object(build, "gh_counts", lambda *a: GH[1]):
            build.main(["--config", str(HERE / "config.example.json"), "--out", str(self.out), "--today", "2026-11-05"])
        self.assertTrue((self.out / "index.html").exists() and (self.out / "README.md").exists())

if __name__ == "__main__":
    unittest.main()
