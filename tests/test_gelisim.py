"""gelisim.py: measuring, safe patching, proposal-only nightly run, apply/patch on yes, 7-day revert. No model calls."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

os.environ["PENTARCH_HOME"] = tempfile.mkdtemp(prefix="pentarch-test-")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import gelisim  # noqa: E402

OWNER, NAME = gelisim.OWNER, gelisim.NAME
KURAL = "# Rules\n- Answer briefly.\n- Ask before sending anything.\n"


class Ortam(unittest.TestCase):
    """Every path of the module points into a fresh temp home; app/ is a temp folder with one module."""

    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        g, app = self.d / "gelisim", self.d / "app"
        app.mkdir()
        (app / "foo.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")
        (self.d / "kurallar.md").write_text(KURAL, encoding="utf-8")
        yollar = {"G": g, "DEGISIKLIK": g / "degisiklikler.json", "GUNLUK": g / "gunluk.jsonl", "YEDEK": g / "yedek",
                  "KURALLAR": self.d / "kurallar.md", "AYARLAR": self.d / "ayarlar.json",
                  "KONUSMA": self.d / "konusma.log", "ROUTING_LOG": self.d / "kademe.jsonl", "APP": app}
        self.p = [mock.patch.object(gelisim, k, v) for k, v in yollar.items()]
        self.p.append(mock.patch.dict(gelisim.C, {"self_improve": {"enabled": True}}))
        for p in self.p:
            p.start()
        t = f"{datetime.now():%Y-%m-%d %H:%M}"
        gelisim.KONUSMA.write_text(f"{t} | {NAME}: I sent the mail to the landlord.\n"
                                   f"{t} | {OWNER}: No, I told you to ask me first!\n"
                                   f"{t} | {NAME}: Done, the summary is ready.\n"
                                   f"{t} | {OWNER}: thanks\n", encoding="utf-8")

    def tearDown(self):
        for p in self.p:
            p.stop()
        shutil.rmtree(self.d, ignore_errors=True)


SINIF = json.dumps({"duzeltmeler": [{"i": 0, "tur": "asks-late"}],
                    "turler": {"asks-late": {"ozet": "sent without asking", "ara": ["hello"]}}})


class Olc(Ortam):
    def test_owner_messages_and_missing_verdicts(self):
        gelisim.ROUTING_LOG.write_text(json.dumps({"t": f"{datetime.now():%Y-%m-%d %H:%M}", "tarif": "write a haiku",
                                                   "adimlar": [{"karar": "MISSING", "neden": "no haiku"}]}) + "\n",
                                       encoding="utf-8")
        say, mesajlar, ornek = gelisim.olc(7)
        self.assertEqual(say, {"eksik": 1})
        self.assertEqual([m["sahip"] for m in mesajlar], ["No, I told you to ask me first!", "thanks"])
        self.assertEqual(mesajlar[0]["asistan"], "I sent the mail to the landlord.")
        self.assertIn("no haiku", ornek["eksik"][0])


class Yamala(unittest.TestCase):
    def test_snippet_must_occur_once(self):
        o = {"tur": "kurallar", "eski": "- Answer briefly.", "yeni": "- Answer briefly, in two sentences."}
        self.assertIn("two sentences", gelisim.yamala(o, KURAL))
        with self.assertRaises(ValueError):
            gelisim.yamala(dict(o, eski="- Missing line."), KURAL)
        with self.assertRaises(ValueError):
            gelisim.yamala(dict(o, eski="- "), KURAL)

    def test_guarded_lines_and_shrinking(self):
        with self.assertRaises(ValueError):
            gelisim.yamala({"tur": "kurallar", "eski": "- Answer briefly.", "yeni": "- Raise max-budget-usd."}, KURAL)
        with self.assertRaises(ValueError):
            gelisim.yamala({"tur": "kurallar", "eski": KURAL[2:], "yeni": "x"}, KURAL)

    def test_setting_bounds(self):
        self.assertEqual(json.loads(gelisim.yamala({"tur": "ayar", "anahtar": "kelime_siniri", "deger": 60}, "")),
                         {"kelime_siniri": 60})
        for v in (5000, True, "60"):
            with self.assertRaises(ValueError):
                gelisim.yamala({"tur": "ayar", "anahtar": "kelime_siniri", "deger": v}, "{}")

    def test_hedef_refuses_protected_files(self):
        for o in ({"tur": "kod", "dosya": "config.py"}, {"tur": "kod", "dosya": "../x.py"},
                  {"tur": "ayar", "anahtar": "otomatik_gunluk_usd"}, {"tur": "sil"}):
            with self.assertRaises(ValueError):
                gelisim.hedef(o)


class Gece(Ortam):
    def test_off_does_nothing(self):
        with mock.patch.dict(gelisim.C, {"self_improve": {"enabled": False}}), \
                mock.patch.object(gelisim.magi, "agent_sor") as m:
            self.assertEqual(gelisim.gece(), {"mesaj": "-", "onay": []})
        m.assert_not_called()

    def test_rule_change_is_only_proposed_then_applied_on_yes(self):
        oneri = json.dumps({"tur": "kurallar", "eski": "- Ask before sending anything.",
                            "yeni": "- Ask before sending anything, mail included.", "neden": "it mailed unasked"})
        with mock.patch.object(gelisim.magi, "agent_sor", side_effect=[SINIF, oneri]):
            r = gelisim.gece()
        self.assertEqual(len(r["onay"]), 1)
        self.assertIn("uygula 1", r["onay"][0]["is"])
        self.assertEqual(gelisim.KURALLAR.read_text(encoding="utf-8"), KURAL)  # nothing changed before the yes
        self.assertIn("mail included", gelisim.uygula(1) + gelisim.KURALLAR.read_text(encoding="utf-8"))
        self.assertTrue((gelisim.YEDEK / "1-kurallar.md").exists())
        self.assertIn("not waiting", gelisim.uygula(1))

    def test_file_changed_after_proposal_is_not_applied(self):
        oneri = json.dumps({"tur": "kurallar", "eski": "- Answer briefly.", "yeni": "- Answer in one line.", "neden": "x"})
        with mock.patch.object(gelisim.magi, "agent_sor", side_effect=[SINIF, oneri]):
            gelisim.gece()
        gelisim.KURALLAR.write_text(KURAL + "- New rule.\n", encoding="utf-8")
        self.assertIn("changed after the proposal", gelisim.uygula(1))
        self.assertNotIn("one line", gelisim.KURALLAR.read_text(encoding="utf-8"))

    def test_code_change_becomes_a_patch_never_an_edit(self):
        oneri = json.dumps({"tur": "kod", "dosya": "foo.py", "eski": "return 'hi'", "yeni": "return 'hello'",
                            "neden": "friendlier"})
        with mock.patch.object(gelisim.magi, "agent_sor", side_effect=[SINIF, oneri]), \
                mock.patch.object(gelisim, "sina", return_value=(True, "OK")) as sina:
            r = gelisim.gece()
        sina.assert_called_once()
        self.assertEqual(len(r["onay"]), 1)
        gelisim.uygula(1)
        self.assertIn("return 'hi'", (gelisim.APP / "foo.py").read_text(encoding="utf-8"))
        yama = (gelisim.G / "1.patch").read_text(encoding="utf-8")
        self.assertIn("-    return 'hi'", yama)
        self.assertIn("+    return 'hello'", yama)

    def test_failing_tests_drop_the_change(self):
        oneri = json.dumps({"tur": "kod", "dosya": "foo.py", "eski": "return 'hi'", "yeni": "return 1/0", "neden": "x"})
        with mock.patch.object(gelisim.magi, "agent_sor", side_effect=[SINIF, oneri]), \
                mock.patch.object(gelisim, "sina", return_value=(False, "1 failed")):
            r = gelisim.gece()
        self.assertEqual(r["onay"], [])
        self.assertEqual(gelisim.degisiklikler()[0]["durum"], "tests failed")

    def test_unhelpful_change_gets_a_revert_proposal(self):
        oneri = json.dumps({"tur": "kurallar", "eski": "- Answer briefly.", "yeni": "- Answer in one line.", "neden": "x"})
        with mock.patch.object(gelisim.magi, "agent_sor", side_effect=[SINIF, oneri]):
            gelisim.gece()
        gelisim.uygula(1)
        dd = gelisim.degisiklikler()
        dd[0]["t_uygula"] = f"{datetime.now() - timedelta(days=8):%Y-%m-%d %H:%M}"
        gelisim.degisiklik_yaz(dd)
        with mock.patch.object(gelisim.magi, "agent_sor", side_effect=[SINIF, json.dumps({"tur": "yok", "neden": "-"})]):
            r = gelisim.gece()
        self.assertIn("geri 1", r["onay"][0]["is"])
        self.assertIn("reverted", gelisim.geri(1))
        self.assertEqual(gelisim.KURALLAR.read_text(encoding="utf-8"), KURAL)


class Fark(unittest.TestCase):
    @unittest.skipUnless(shutil.which("git"), "git not installed")
    def test_patch_applies_with_git(self):
        eski, yeni = "a = 1\nb = 2\n", "a = 1\nb = 3\n"
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "app").mkdir()
            (Path(d) / "app" / "x.py").write_text(eski, encoding="utf-8")
            (Path(d) / "x.patch").write_text(gelisim.fark(eski, yeni, "x.py"), encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=d, check=True)
            p = subprocess.run(["git", "apply", "x.patch"], cwd=d, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual((Path(d) / "app" / "x.py").read_text(encoding="utf-8"), yeni)


if __name__ == "__main__":
    unittest.main()
