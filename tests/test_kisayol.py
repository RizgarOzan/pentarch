"""Shortcuts: saved, run without a model, guarded against names that hide real commands."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HOME = tempfile.mkdtemp(prefix="pentarch-kisayol-")
os.environ["PENTARCH_HOME"] = HOME
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
import kisayol  # noqa: E402


class KisayolTest(unittest.TestCase):
    def setUp(self):
        kisayol.DOSYA.unlink(missing_ok=True)

    def test_add_list_run_remove(self):
        self.assertIn("sabah", kisayol.komut("kısayol ekle sabah = alacak + shifts"))
        self.assertEqual(kisayol.oku()[0]["adimlar"], ["alacak", "vardiya"])
        self.assertIn("sabah: alacak + vardiya", kisayol.komut("kısayol liste"))
        with mock.patch.object(kisayol, "_calistir", side_effect=lambda a: f"çıktı-{a}"):
            out = kisayol.komut("/sabah")
        self.assertIn("— alacak —\nçıktı-alacak", out)
        self.assertIn("çıktı-vardiya", out)
        kisayol.komut("kısayol sil sabah")
        self.assertEqual(kisayol.oku(), [])
        self.assertIsNone(kisayol.komut("sabah"))

    def test_single_reader_has_no_header(self):
        kisayol.komut("shortcut add borclar = alacak")
        with mock.patch.object(kisayol, "_calistir", return_value="toplam 5"):
            self.assertEqual(kisayol.komut("borclar"), "toplam 5")

    def test_reserved_and_bad_names_are_refused(self):
        for ad in ("yardım", "iptal", "alacak", "ab", "evet"):
            self.assertIn("not saved" if "not saved" in kisayol.komut(f"shortcut add {ad} = ders") else "kaydedilmedi",
                          kisayol.komut(f"shortcut add {ad} = ders"))
        self.assertEqual(kisayol.oku(), [])

    def test_unknown_reader_is_refused(self):
        self.assertIn("rm", kisayol.komut("kısayol ekle temizle = rm"))
        self.assertEqual(kisayol.oku(), [])

    def test_a_broken_reader_does_not_stop_the_others(self):
        kisayol.komut("kısayol ekle gun = ders + alacak")
        def fake(a):
            if a == "ders":
                raise OSError("bozuk")
            return "tamam"
        with mock.patch.object(kisayol, "_calistir", side_effect=fake):
            out = kisayol.komut("gun")
        self.assertIn("bozuk", out)
        self.assertIn("tamam", out)

    def test_long_or_unrelated_text_goes_to_the_model(self):
        kisayol.komut("kısayol ekle sabah = ders")
        self.assertIsNone(kisayol.komut("sabah bana bir şey anlat " * 3))
        self.assertIsNone(kisayol.komut("merhaba"))

    def test_nudge_drafts_only_for_overdue_money_owed_to_us(self):
        import datetime
        import alacak
        metin = "\n".join(["2026-11-01 | Ahmet Kafe | 4500", "2026-12-30 | Gelecek | 100",
                           "borc 2026-11-02 | Toptanci | 900", "- [x] 2026-11-03 | Odenmis | 50"])
        out = alacak.taslaklar(metin, datetime.date(2026, 11, 20))
        self.assertIn("Ahmet Kafe", out)
        for kisi in ("Gelecek", "Toptanci", "Odenmis"):
            self.assertNotIn(kisi, out)
        kisayol.komut("kısayol ekle tahsil = nudges")
        self.assertEqual(kisayol.oku()[0]["adimlar"], ["tahsilat"])


class YanitTest(unittest.TestCase):
    ROWS = [{"id": "acme-dev", "company": "Acme Labs", "stage": "sent"},
            {"id": "old", "company": "Globex", "stage": "closed"},
            {"id": "x", "company": "Ab", "stage": "sent"}]

    def test_rejection_interview_offer(self):
        import yanit
        o = yanit.oneriler(["HR <jobs@acmelabs.com> | Your application | Unfortunately we are not moving forward"], self.ROWS)
        self.assertEqual(o, [("acme-dev", "Acme Labs", "closed")])
        o = yanit.oneriler(["Acme Labs <hr@a.com> | Interview invitation | pick a time"], self.ROWS)
        self.assertEqual(o[0][2], "process")
        o = yanit.oneriler(["Acme Labs <hr@a.com> | We are pleased to offer you the role"], self.ROWS)
        self.assertEqual(o[0][2], "decide")

    def test_rejection_beats_interview_and_unrelated_mail_is_ignored(self):
        import yanit
        self.assertEqual(yanit.oneriler(["Acme Labs | interview | unfortunately no"], self.ROWS)[0][2], "closed")
        self.assertEqual(yanit.oneriler(["Newsletter <n@x.com> | Weekly digest"], self.ROWS), [])

    def test_closed_rows_and_tiny_names_never_match(self):
        import yanit
        self.assertEqual(yanit.oneriler(["Globex | unfortunately", "Ab | interview"], self.ROWS), [])


if __name__ == "__main__":
    unittest.main()
