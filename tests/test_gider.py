"""Expense ledger: add in plain words, monthly total, bad input refused."""
import datetime
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

NOTES = tempfile.mkdtemp(prefix="pentarch-gider-")
os.environ["PENTARCH_HOME"] = tempfile.mkdtemp(prefix="pentarch-gider-home-")
os.environ["PENTARCH_NOTES_DIR"] = NOTES
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import gider  # noqa: E402


class GiderTest(unittest.TestCase):
    def setUp(self):
        # config is imported once per test run, so the notes folder is pinned here instead of through the environment
        for f in Path(NOTES).glob("*"):
            f.unlink()
        p = mock.patch.object(gider, "NOTES", Path(NOTES))
        p.start()
        self.addCleanup(p.stop)

    def test_add_and_monthly_total(self):
        self.assertIn("Added", gider.komut('expense add flour 1200 weekly'))
        self.assertIn("Added", gider.komut('gider ekle "Un Toptan" 800'))
        self.assertIn("Added", gider.komut("gider ekle flour 300"))
        out = gider.cli()
        self.assertIn("2,300", out)  # 1200 + 800 + 300
        self.assertIn("flour 1,500", out.lower())  # same name adds up
        self.assertIn("Last month", out)

    def test_last_month_is_separate(self):
        f = Path(NOTES) / "expenses.md"
        f.write_text("2026-10-05 | rent | 5000\n2026-11-02 | flour | 100\n", encoding="utf-8")
        out = gider.ozet(f.read_text(encoding="utf-8"), datetime.date(2026, 11, 20))
        self.assertIn("This month (2026-11): 100", out)
        self.assertIn("Last month (2026-10): 5,000", out)
        self.assertNotIn("rent", out)

    def test_bad_input_is_refused_and_writes_nothing(self):
        for bad in ("gider ekle un", "gider ekle un abc", "gider ekle un 1|2", "gider ekle un 99999999999999999"):
            self.assertIn("Usage", gider.komut(bad))
        self.assertFalse(list(Path(NOTES).glob("*")))

    def test_no_file_and_unrelated_text(self):
        self.assertIn("No expense file", gider.komut("expenses"))
        self.assertIsNone(gider.komut("gider ne kadar oldu bu ay"))
        self.assertIsNone(gider.komut("merhaba"))

    def test_unreadable_line_is_reported(self):
        (Path(NOTES) / "expenses.md").write_text("2026-11-02 | flour | 100\n2026-11-03 | x | abc\n", encoding="utf-8")
        self.assertIn("WARNING", gider.cli())


if __name__ == "__main__":
    unittest.main()
