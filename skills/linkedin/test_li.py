# -*- coding: utf-8 -*-
"""Tests for li.py. No network, temp dir as home.  python -I skills/linkedin/test_li.py"""
import datetime, io, json, pathlib, sys, tempfile, unittest
from contextlib import redirect_stdout

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import li

TODAY = datetime.date(2026, 11, 5)
GOOD = """I got 0 replies from 40 cold applications. Then I changed one thing.

I stopped sending the CV first and started sending a 3-line note about their product.

Replies went from 0 to 6 in two weeks.

Which line of your message gets the reply?"""


def levels(rows):
    return {msg.split(";")[0]: lvl for lvl, msg in rows}


class Check(unittest.TestCase):
    def test_good_post_passes(self):
        rows = li.check_text(GOOD)
        self.assertNotIn("FAIL", [l for l, _ in rows])
        self.assertNotIn("WARN", [l for l, _ in rows], rows)
        self.assertTrue(rows[0][1].startswith("fold preview"))

    def test_warnings(self):
        bad = "I'm thrilled to announce that I will leverage this journey — see https://x.y #a #b #c #d\n" + "word " * 100
        rows = li.check_text(bad)
        text = " ".join(m for _, m in rows)
        for part in ("link in the body", "4 hashtags", "does not end with a question", "thrilled to announce", "em dash", "leverage -> use", "one block of text"):
            self.assertIn(part, text)

    def test_turkish_tells(self):
        rows = li.check_text("Heyecanla paylaşıyorum: yeni bir yolculuk başlıyor.\n\nNe dersiniz?")
        self.assertIn("heyecanla paylaşıyorum", " ".join(m for _, m in rows))

    def test_hard_limit_fails(self):
        rows = li.check_text("a" * 3001)
        self.assertIn("FAIL", [l for l, _ in rows])


class Profile(unittest.TestCase):
    def test_full_profile_scores_100(self):
        p = dict(headline="Junior game dev | Unity, C# | shipped 2 jam games", about="Hook with 3 numbers? " + "word " * 160,
                 featured=3, banner=True, photo_px=800, experience=[{"title": "Dev", "bullets": ["Cut load time 40%", "Shipped 2 builds"]}],
                 skills=["s%d" % i for i in range(25)], pinned_skills=["a", "b", "c"], recommendations=3, posts_30d=4, comments_30d=5,
                 custom_url=True, contact="email")
        total, rows = li.score_profile(p)
        self.assertEqual(total, 100, rows)

    def test_empty_profile_scores_0(self):
        self.assertEqual(li.score_profile({})[0], 0)

    def test_partial(self):
        total, rows = li.score_profile(dict(headline="x" * 250, about="short", experience=[{"title": "a", "bullets": []}]))
        got = dict((k, g) for k, g, _, _ in rows)
        self.assertEqual(got["headline"], 6)          # present but over 220 and no separator/number
        self.assertEqual(got["about_body"], 2)
        self.assertEqual(got["experience_depth"], 4)
        self.assertLess(total, 30)


class State(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.h = li.home(self.tmp.name)
        self.post = pathlib.Path(self.tmp.name) / "p.txt"; self.post.write_text(GOOD, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_log_round_trip(self):
        a = li.log_add(self.h, "Number Reveal", "authority", str(self.post), "2026-11-01")
        b = li.log_add(self.h, "Story Cold Open", "narrative", None, "2026-11-03")
        c = li.log_add(self.h, "Number Reveal", "authority", None, "2026-11-04")
        self.assertEqual((a["id"], b["id"], c["id"]), (1, 2, 3)); self.assertEqual(a["chars"], len(GOOD))
        li.log_result(self.h, 1, views=1000, comments=10); li.log_result(self.h, 2, views=200, comments=1); li.log_result(self.h, 3, views=600, comments=4)
        stats, n = li.log_stats(self.h)
        self.assertEqual(n, 3)
        self.assertEqual(stats["hook"][0][0], "Number Reveal"); self.assertEqual(stats["hook"][0][1], 2); self.assertEqual(stats["hook"][0][2], 800)
        self.assertEqual([k for k, *_ in stats["pillar"]], ["authority", "narrative"])
        with self.assertRaises(SystemExit):
            li.log_result(self.h, 9, views=1)
        self.assertEqual(json.loads((self.h / "log.json").read_text(encoding="utf-8"))[0]["views"], 1000)

    def test_network_due(self):
        a = li.net_add(self.h, "A", "Acme", "recruiter", 7, TODAY)
        b = li.net_add(self.h, "B", "Zed", "peer", 30, TODAY)
        self.assertEqual(a["next"], "2026-11-12")
        self.assertEqual(li.net_due(self.h, TODAY), [])
        due = li.net_due(self.h, TODAY + datetime.timedelta(days=8))
        self.assertEqual([r["name"] for r in due], ["A"])
        t = li.net_touch(self.h, a["id"], 14, "sent the note", TODAY + datetime.timedelta(days=8))
        self.assertEqual((t["touches"], t["next"], t["note"]), (1, "2026-11-27", "sent the note"))
        self.assertEqual(li.net_due(self.h, TODAY + datetime.timedelta(days=8)), [])
        self.assertEqual([r["name"] for r in li.net_due(self.h, TODAY + datetime.timedelta(days=40))], ["A", "B"])

    def test_cli(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(li.main(["--home", self.tmp.name, "check", str(self.post)]), 0)
            self.assertEqual(li.main(["--home", self.tmp.name, "log", "add", "--hook", "List Promise", "--pillar", "community", "--file", str(self.post)]), 0)
            self.assertEqual(li.main(["--home", self.tmp.name, "log", "result", "1", "--views", "50"]), 0)
            self.assertEqual(li.main(["--home", self.tmp.name, "log", "stats"]), 0)
            self.assertEqual(li.main(["--home", self.tmp.name, "network", "add", "--name", "N", "--company", "C", "--why", "w", "--days", "0"]), 0)
            self.assertEqual(li.main(["--home", self.tmp.name, "network", "due"]), 0)
        text = out.getvalue()
        for part in ("PASS", "logged post 1", "50 views", "List Promise", "1 due", "N (C)"):
            self.assertIn(part, text)
        self.assertFalse((pathlib.Path(self.tmp.name) / "linkedin").exists())   # --home is used as-is

    def test_home_default_under_pentarch_home(self):
        import os
        old = os.environ.get("PENTARCH_HOME"); os.environ["PENTARCH_HOME"] = self.tmp.name
        try:
            self.assertEqual(li.home(), pathlib.Path(self.tmp.name) / "linkedin")
        finally:
            if old is None: del os.environ["PENTARCH_HOME"]
            else: os.environ["PENTARCH_HOME"] = old


if __name__ == "__main__":
    unittest.main()
