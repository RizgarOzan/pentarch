"""agent.cli = "api": the built-in tool loop, with a fake endpoint (no network, notes folder in a temp dir).

  python -I -m unittest discover -s tests -p "test_*.py"
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("PENTARCH_HOME", tempfile.mkdtemp(prefix="pentarch-api-"))
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
import agents  # noqa: E402
import api_ajan  # noqa: E402

API = {"base_url": "http://local/v1", "model": "m", "trusted": True}


def cagri(ad, **girdi):
    return {"role": "assistant", "content": "", "tool_calls": [
        {"id": "c1", "type": "function", "function": {"name": ad, "arguments": json.dumps(girdi)}}]}


class ApiAjan(unittest.TestCase):
    def setUp(self):
        self.notes = Path(tempfile.mkdtemp(prefix="notes-"))
        self.home = Path(tempfile.mkdtemp(prefix="home-"))
        (self.home / "secrets").mkdir()
        (self.home / "secrets" / "keys.env").write_text("X=1", encoding="utf-8")
        (self.notes / "a.md").write_text("elma", encoding="utf-8")
        for ad, deger in (("NOTES", self.notes), ("HOME", self.home), ("SECRETS", self.home / "secrets"), ("EXTRA_DIRS", [])):
            p = mock.patch.object(api_ajan, ad, deger)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(agents, "providers", return_value=[API])
        p.start()
        self.addCleanup(p.stop)

    def sahte(self, cevaplar):
        """istek stand-in: hands back the queued messages in order and records what it was sent."""
        self.gonderilen = []

        def istek(api, mesajlar, **kw):
            self.gonderilen.append((list(mesajlar), kw))
            c = cevaplar.pop(0)
            if isinstance(c, Exception):
                raise c
            return c, {}
        return mock.patch.object(agents, "istek", side_effect=istek)

    def test_reads_a_note_then_answers(self):
        with self.sahte([cagri("read_file", path="a.md"), {"role": "assistant", "content": "notta elma var"}]):
            r = api_ajan.calistir("notta ne var?")
        self.assertFalse(r["is_error"])
        self.assertEqual(r["result"], "notta elma var")
        tool = self.gonderilen[1][0][-1]
        self.assertEqual((tool["role"], tool["content"]), ("tool", "elma"))
        self.assertTrue(self.gonderilen[0][1]["kisisel"])  # the chat counts as personal data

    def test_secrets_and_outside_paths_are_refused(self):
        for yol in (str(self.home / "secrets" / "keys.env"), "../../etc/passwd", str(Path(tempfile.gettempdir()))):
            out = api_ajan.calistir_arac("read_file", {"path": yol}, None, False)
            self.assertIn("not allowed", out.replace("izin yok", "not allowed"), yol)
        self.assertIn("not a file", api_ajan.calistir_arac("read_file", {"path": str(self.home / "x.txt")}, None, False)
                      .replace("dosya değil", "not a file"))

    def test_write_refuses_dot_folders_streams_and_non_text(self):
        for yol in (".git/config", ".claude/settings.json", ".obsidian/plugins/x/main.js", "n.md:evil", "x.py", "alt/.gizli.md"):
            api_ajan.calistir_arac("write_file", {"path": yol, "content": "x"}, None, False)
        self.assertEqual(sorted(p.name for p in self.notes.rglob("*")), ["a.md"])
        self.assertIn(api_ajan.calistir_arac("write_file", {"path": "alt/b.TXT", "content": "x"}, None, False), ("yazıldı", "written"))

    def test_no_failover_after_a_tool_ran(self):
        p = mock.patch.object(agents, "providers", return_value=[API, dict(API, base_url="http://iki/v1")])
        p.start()
        self.addCleanup(p.stop)
        with mock.patch.object(api_ajan, "calistir_arac", return_value="eklendi") as arac, \
                self.sahte([cagri("pentarch", args=["task", "now", "x"]), RuntimeError("http://local/v1 HTTP 500: boom"),
                            cagri("pentarch", args=["task", "now", "x"]), {"role": "assistant", "content": "tamam"}]):
            r = api_ajan.calistir("bir görev ekle")
        self.assertTrue(r["is_error"])
        self.assertEqual(arac.call_count, 1)  # the task was queued once, not again on the second provider

    def test_reading_run_cannot_queue_tasks(self):
        with mock.patch.object(api_ajan.subprocess, "run") as run:
            api_ajan.calistir_arac("pentarch", {"args": ["task", "now", "x"]}, "oto", True)
        run.assert_not_called()

    def test_only_tool_errors_drop_the_tools(self):
        with self.sahte([RuntimeError("http://local/v1 HTTP 401: bad key")]):
            r = api_ajan.calistir("selam")
        self.assertTrue(r["is_error"])
        self.assertEqual(len(self.gonderilen), 1)

    def test_write_only_in_notes_and_never_on_scheduled_runs(self):
        self.assertIn(api_ajan.calistir_arac("write_file", {"path": "b.md", "content": "x"}, None, False), ("yazıldı", "written"))
        self.assertEqual((self.notes / "b.md").read_text(encoding="utf-8"), "x")
        out = api_ajan.calistir_arac("write_file", {"path": str(self.home / "c.md"), "content": "x"}, None, False)
        self.assertFalse((self.home / "c.md").exists(), out)
        api_ajan.calistir_arac("write_file", {"path": "d.md", "content": "x"}, None, True)
        self.assertFalse((self.notes / "d.md").exists())
        self.assertNotIn("write_file", [a["function"]["name"] for a in api_ajan.araclar(True)])

    def test_command_allowlist(self):
        with mock.patch.object(api_ajan.subprocess, "run") as run:
            self.assertIn("not available", api_ajan.calistir_arac("pentarch", {"args": ["update"]}, None, False)
                          .replace("bu komut burada yok", "not available"))
            api_ajan.calistir_arac("pentarch", {"args": ["routine", "add", "x", "09:00", "y"]}, None, True)
            run.assert_not_called()  # a reading run can't add routines
            run.return_value = mock.Mock(stdout="ok", stderr="")
            api_ajan.calistir_arac("pentarch", {"args": ["remind", "2026-11-21 09:00", "süt"]}, "telegram", False)
            self.assertEqual(run.call_args.kwargs["env"]["PENTARCH_KIND"], "telegram")

    def test_reading_run_gets_no_tools(self):
        with self.sahte([{"role": "assistant", "content": "özet"}]):
            r = api_ajan.calistir("bu maili özetle", salt_okur=True)
        self.assertEqual(r["result"], "özet")
        self.assertIsNone(self.gonderilen[0][1]["ek"])

    def test_model_without_tools_falls_back_to_plain_chat(self):
        with self.sahte([RuntimeError("http://local/v1 HTTP 400: tools not supported"), {"role": "assistant", "content": "selam"}]):
            r = api_ajan.calistir("selam")
        self.assertEqual(r["result"], "selam")
        self.assertIsNotNone(self.gonderilen[0][1]["ek"])
        self.assertIsNone(self.gonderilen[1][1]["ek"])

    def test_session_is_kept_and_resumed(self):
        with self.sahte([{"role": "assistant", "content": "bir"}]):
            sid = api_ajan.calistir("ilk", keep=True)["session_id"]
        self.assertTrue(api_ajan._oturum(sid).exists())
        with self.sahte([{"role": "assistant", "content": "iki"}]):
            api_ajan.calistir("ikinci", resume=sid, keep=True)
        self.assertEqual([m["content"] for m in self.gonderilen[0][0]], ["ilk", "bir", "ikinci"])

    def test_trim_starts_at_a_user_message(self):
        m = [{"role": "tool", "content": "x"}, {"role": "assistant", "content": "y"}, {"role": "user", "content": "z"}]
        self.assertEqual(api_ajan._kirp(m)[0]["role"], "user")
        uzun = [{"role": "user", "content": "u"}] + [{"role": "tool", "content": "t"}] * (api_ajan.GECMIS + 5)
        self.assertEqual(len(api_ajan._kirp(uzun)), len(uzun))  # one long tool chain is kept, not dropped

    def test_untrusted_only_providers_explain_the_fix(self):
        with self.sahte([PermissionError("refusing to send personal data to http://x")]):
            r = api_ajan.calistir("selam")
        self.assertTrue(r["is_error"])
        self.assertIn("trusted", r["result"])

    def test_think_blocks_are_stripped(self):
        self.assertEqual(agents.DUSUNCE_RE.sub("", "<think>hmm</think>cevap").strip(), "cevap")


if __name__ == "__main__":
    unittest.main()
