"""sirket.py: tier choice, machine checks, the cheap -> mid -> top flow and the routing log. No model or network calls."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ["PENTARCH_HOME"] = tempfile.mkdtemp(prefix="pentarch-test-")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import sirket  # noqa: E402

KOD = "```python\ndef kare(x):\n    return x * x\nassert kare(2) == 4\n```"


class KademeSec(unittest.TestCase):
    def test_top_only_from_owner_or_architecture(self):
        self.assertEqual(sirket.kademe_sec("summarise this", "do it in depth please")[0], "top")
        self.assertEqual(sirket.kademe_sec("refactor the scheduler")[0], "top")
        self.assertEqual(sirket.kademe_sec("change code in 4 files")[0], "top")
        self.assertEqual(sirket.kademe_sec("mimariyi değiştir")[0], "top")
        # a model name in the job text is a hint, not a decision
        self.assertNotEqual(sirket.kademe_sec(f"let a separate {sirket.DEEP} estimate it")[0], "top")

    def test_mid_for_tools_personal_or_unchecked(self):
        self.assertEqual(sirket.kademe_sec("reply to the e-mail from the landlord", sinanir=True)[0], "mid")
        self.assertEqual(sirket.kademe_sec("open https://example.com and read it", sinanir=True)[0], "mid")
        self.assertEqual(sirket.kademe_sec("write a haiku")[0], "mid")

    def test_cheap_needs_a_machine_check(self):
        self.assertEqual(sirket.kademe_sec("write kare(x)\nassert kare(3) == 9", sinanir=True)[0], "cheap")


class Sinama(unittest.TestCase):
    def test_testleri_ayikla(self):
        self.assertEqual(sirket.testleri_ayikla("do it; assert f(1) == 1; assert f(2) == 4\nmore"),
                         "assert f(1) == 1\nassert f(2) == 4")

    def test_kod_sina(self):
        self.assertTrue(sirket.kod_sina(KOD, "assert kare(3) == 9")[0])
        self.assertFalse(sirket.kod_sina(KOD, "assert kare(3) == 10")[0])
        self.assertFalse(sirket.kod_sina("import os\nassert True")[0])
        self.assertFalse(sirket.kod_sina("def f(:\n")[0])

    def test_sema_and_kaynak(self):
        self.assertTrue(sirket.sema_sina('{"a": "x", "b": 2}', {"a": "str", "b": "int|null"})[0])
        self.assertFalse(sirket.sema_sina('{"a": "x"}', {"a": "str", "b": "int"})[0])
        self.assertFalse(sirket.sema_sina('{"a": true}', {"a": "int"})[0])
        self.assertTrue(sirket.kaynak_sina('{"city": "Paris", "n": 3.0}', "Trip to PARIS for 3 days")[0])
        self.assertFalse(sirket.kaynak_sina('{"city": "Rome"}', "Trip to Paris")[0])


class Kos(unittest.TestCase):
    def setUp(self):
        d = Path(tempfile.mkdtemp())
        self.p = [mock.patch.object(sirket, "KAYIT", d / "kademe.jsonl"),
                  mock.patch.dict(sirket.C, {"routing": {"enabled": True}})]
        for p in self.p:
            p.start()
        self.run = mock.Mock(return_value="done: added the section")

    def tearDown(self):
        for p in self.p:
            p.stop()

    def test_off_runs_once_on_default_model(self):
        with mock.patch.dict(sirket.C, {"routing": {"enabled": False}}):
            self.assertEqual(sirket.kos("P", "write a haiku", "", self.run), "done: added the section")
        self.run.assert_called_once_with("P", None)
        self.assertFalse(sirket.KAYIT.exists())

    def test_mid_reviewed_ok(self):
        with mock.patch.object(sirket.magi, "agent_sor", return_value="OK") as rev:
            self.assertEqual(sirket.kos("P", "write a haiku", "haiku pls", self.run, no=7), "done: added the section")
        self.run.assert_called_once_with("P", sirket.FAST)
        rev.assert_called_once()
        self.assertIn('"son": "mid"', sirket.KAYIT.read_text(encoding="utf-8"))

    def test_missing_escalates_with_the_attempt(self):
        self.run.side_effect = ["half done", "all done"]
        with mock.patch.object(sirket.magi, "agent_sor", return_value="MISSING: the second part is not there"):
            self.assertEqual(sirket.kos("P", "write a haiku", "", self.run), "all done")
        prompt, model = self.run.call_args_list[1].args
        self.assertEqual(model, sirket.DEEP)
        self.assertIn("the second part is not there", prompt)
        self.assertIn("half done", prompt)
        self.assertIn("review found it incomplete", sirket.ozet())

    def test_reviewer_failure_counts_as_fine(self):
        with mock.patch.object(sirket.magi, "agent_sor", side_effect=RuntimeError("down")):
            sirket.kos("P", "write a haiku", "", self.run)
        self.run.assert_called_once()

    def test_top_skips_review(self):
        with mock.patch.object(sirket.magi, "agent_sor") as rev:
            sirket.kos("P", "refactor the scheduler", "", self.run)
        rev.assert_not_called()
        self.run.assert_called_once_with("P", sirket.DEEP)

    def test_cheap_passes_without_agent_run(self):
        api = {"base_url": "http://x", "model": "small"}
        with mock.patch.object(sirket.agents, "providers", return_value=[api]), \
                mock.patch.object(sirket.agents, "istek", return_value=(KOD, {})), \
                mock.patch.object(sirket.magi, "agent_sor", return_value="OK"):
            self.assertEqual(sirket.kos("P", "write kare(x)\nassert kare(3) == 9", "", self.run), KOD)
        self.run.assert_not_called()

    def test_cheap_failing_checks_moves_to_mid(self):
        api = {"base_url": "http://x", "model": "small"}
        bad = "```python\ndef kare(x):\n    return x\nassert True\n```"
        with mock.patch.object(sirket.agents, "providers", return_value=[api]), \
                mock.patch.object(sirket.agents, "istek", return_value=(bad, {})) as ist, \
                mock.patch.object(sirket.magi, "agent_sor", return_value="OK"):
            sirket.kos("P", "write kare(x)\nassert kare(3) == 9", "", self.run)
        self.assertEqual(ist.call_count, sirket.KADEME_HAK)
        self.run.assert_called_once_with("P", sirket.FAST)

    def test_stopped_job_is_not_escalated(self):
        with mock.patch.object(sirket.magi, "agent_sor") as rev:
            sirket.kos("P", "write a haiku", "", self.run, durdu=lambda: True)
        rev.assert_not_called()
        self.run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
