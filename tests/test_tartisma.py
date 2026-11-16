"""tartisma.py: parsing helpers and the full debate flow with every seat and model call mocked."""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ["PENTARCH_HOME"] = tempfile.mkdtemp(prefix="pentarch-test-")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import tartisma  # noqa: E402


def fikirler(n, ad):
    return "\n".join(f"{i}. {ad} idea {i} :: a one-sentence pitch :: something unusual" for i in range(1, n + 1))


class Ayiklama(unittest.TestCase):
    def test_fikirleri_ayikla_prefers_the_asked_format(self):
        c = "<think>1. draft thought that is long enough</think>\nSome intro\n1. Plain line without the format here\n" \
            + fikirler(3, "X") + "\n3. X idea 3 :: a newer pitch :: still unusual"
        out = tartisma.fikirleri_ayikla(c, 7)
        self.assertEqual(len(out), 3)
        self.assertIn("newer pitch", out[-1])
        self.assertTrue(all("::" in f for f in out))

    def test_oy_say(self):
        t2 = {"A": "text K9\nOY: K2, Y1, K1", "B": "OY: K2, K2, K7, K1", "C": "no vote line"}
        self.assertEqual(tartisma.oy_say(t2, {"K1", "K2", "Y1"}), {"K2": 6, "Y1": 2, "K1": 3})

    def test_puanlari_ayikla_skips_out_of_range(self):
        c = "K1 | 8 | 7 | 6,5 | 9 | 40 | good\nK2 | 11 | 7 | 6 | 9 | 40 | bad\nK3 | 8 | 7 | 6 | 9 | 900 | bad\nK4 | 5 | 5 | 5 | 5 | 5 | x"
        self.assertEqual(tartisma.puanlari_ayikla(c, {"K1", "K2", "K3"}), {"K1": [8, 7, 6.5, 9, 40]})

    def test_iraksak_and_kalabalik(self):
        fikir, atilan = tartisma.iraksak({"A": fikirler(7, "A"), "B": fikirler(5, "B"), "C": "(no answer: down)"})
        self.assertEqual(sorted(atilan), ["M00.d1", "M00.d2"])
        self.assertEqual(len(fikir), 10)
        self.assertIn("A idea 3", fikir["M00.1"][1])
        self.assertEqual(tartisma.kalabalik({"uyeler": ["M00.1", "M00.d1", "M01.2"]}, fikir, atilan), 2)

    def test_parcala_keeps_everything(self):
        metin = ("line " * 30 + "\n") * 200 + "x" * 9000
        parts = tartisma.parcala(metin)
        self.assertEqual("".join(parts), metin)
        self.assertTrue(all(len(p) <= 3800 for p in parts))


KUMELER = [{"k": "K1", "baslik": "One", "ozet": "o", "uyeler": ["M00.1"], "potansiyel": 6},
           {"k": "K2", "baslik": "Two", "ozet": "t", "uyeler": ["M01.1", "M00.2"], "potansiyel": 9},
           {"k": "K3", "baslik": "Crowd", "ozet": "c", "uyeler": ["M00.3", "M01.2", "M02.1"], "potansiyel": 10},
           {"k": "K4", "baslik": "Four", "ozet": "f", "uyeler": ["M02.2"], "potansiyel": 3},
           {"k": "K5", "baslik": "Dropped", "ozet": "d", "uyeler": ["M00.d1"], "potansiyel": 8}]


def koltuk(u, sistem, metin):
    if u == "D":
        raise RuntimeError("seat down")
    if tartisma.ISTEM_A in sistem:
        return fikirler(7, u)
    if tartisma.ISTEM_B in sistem:
        return fikirler(5, u)
    if tartisma.ELESTIRI1 in sistem:
        return "K1 | too small | users\nNEW :: K1+K2 :: Merge :: both at once"
    if tartisma.ELESTIRI2 in sistem:
        return "K2 holds up.\nOY: K2, Y1, K1"
    if tartisma.PUAN_ISTEM in sistem:
        return "\n".join(f"{i} | 8 | 7 | 6 | 9 | 30 | ok" for i in re.findall(r"^([KY]\d+):", metin, re.M))
    raise AssertionError(sistem)


def model(ad, sistem, metin):
    if sistem == tartisma.KUME_ISTEM:
        return "Here:\n" + json.dumps(KUMELER)
    if sistem == tartisma.OZET_ISTEM:
        return json.dumps({"elestiri": {"K1": ["too small"]}, "yeni": [{"k": "Y1", "baslik": "Merge", "ozet": "both"}]})
    assert ad == "deep_model"
    return "Pick K2: it scored best."


class Kos(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        seats = {u: {"kind": "agent", "model": "m", "role": "r"} for u in "ABCD"}
        self.p = [mock.patch.dict(tartisma.magi.UYELER, seats, clear=True),
                  mock.patch.object(tartisma, "sor", side_effect=koltuk),
                  mock.patch.object(tartisma, "model", side_effect=model)]
        self.mocks = [p.start() for p in self.p]

    def tearDown(self):
        for p in self.p:
            p.stop()
        shutil.rmtree(self.d, ignore_errors=True)

    def test_full_debate(self):
        sonuc = tartisma.kos("a tool for small libraries", klasor=self.d)
        sor = self.mocks[1]
        self.assertIn("Pick K2", sonuc)
        self.assertIn("3/4", sonuc)
        # the seat that failed round 1 is never asked again: 4 seats in round 1, then 3 seats x 3 rounds
        self.assertEqual(sor.call_count, 4 + 3 * 3)
        self.assertEqual([c.args[0] for c in sor.call_args_list].count("D"), 1)
        puan_metni = next(c.args[2] for c in sor.call_args_list if tartisma.PUAN_ISTEM in c.args[1])
        self.assertNotIn("K3:", puan_metni)  # three seats found it: crowded
        self.assertNotIn("K5:", puan_metni)  # only an "obvious" dropped idea
        self.assertIn("Y1:", puan_metni)  # the merge from round 1 made it in
        self.assertRegex(sonuc, r"K2 Two: Impact 8, .* votes 9|K2 Two: Impact 8, .* oy 9")
        kayit = list(self.d.glob("*.md"))
        self.assertEqual(len(kayit), 1)
        self.assertIn("Pick K2", kayit[0].read_text(encoding="utf-8"))

    def test_no_ideas_still_writes_the_record(self):
        self.mocks[1].side_effect = RuntimeError("all down")
        with self.assertRaises(RuntimeError):
            tartisma.kos("topic", klasor=self.d)
        self.mocks[2].assert_not_called()
        self.assertIn("RuntimeError", next(self.d.glob("*.md")).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
