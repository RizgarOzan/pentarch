"""menajer.py with no network and no agent: the model runner, GitHub and the subprocesses are fakes."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("PENTARCH_HOME", tempfile.mkdtemp(prefix="pentarch-menajer-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import menajer  # noqa: E402

POSTING = "We build payment APIs in Python and PostgreSQL. Must have: Python, Docker. Send questions to jobs@acme.io."
JOB = dict(id="acme-backend-engineer", company="Acme", role="Backend Engineer", link="https://acme.io/j/1", score=8, text=POSTING)
REVIEW_LOW = {"scores": {"posting_match": {"score": 10}, "impact": {"score": 10}, "projects": {"score": 10},
                         "production": {"score": 5}, "clarity": {"score": 10}}, "deductions": [], "fixes": ["measure bullet 1"], "gaps": ["Docker"]}
REVIEW_HIGH = {"scores": {"posting_match": {"score": 28}, "impact": {"score": 18}, "projects": {"score": 18},
                          "production": {"score": 12}, "clarity": {"score": 14}}, "deductions": [], "fixes": [], "gaps": []}


def fake_runner(reviews, guessed_to=False):
    calls = []

    def kos(prompt, model=None, cli=None, araclar=True):
        assert araclar is False, "every menajer prompt carries a posting: it must run without tools"
        calls.append((prompt.split("]")[0] + "]", cli))
        if prompt.startswith("[Application package]"):
            to = "cto@acme.io" if guessed_to else "jobs@acme.io"
            out = {"email": {"to": to, "subject": "Backend role", "body": "Hi"}, "linkedin_note": "Hi", "who_to_contact": "Engineering manager"}
            return {"result": f"=== CV ===\n```markdown\n# Ada\n- Built X\n```\n=== COVER ===\nDear Acme\n=== OUTREACH ===\n{json.dumps(out)}"}
        if prompt.startswith("[CV review]"):
            return {"result": "here: " + json.dumps(reviews.pop(0))}
        if prompt.startswith("[CV revision]"):
            return {"result": "=== CV ===\n# Ada\n- Cut p95 latency 40% by caching X"}
        raise AssertionError(prompt[:40])
    return kos, calls


class Total(unittest.TestCase):
    def test_caps_and_fixed_deductions(self):
        r = {"scores": {"posting_match": {"score": 99}, "impact": {"score": "12"}, "projects": {"score": -4}, "clarity": "x"},
             "deductions": [{"kind": "invented_fact"}, {"kind": "made_up_kind"}]}
        score, ded = menajer.total(r)
        self.assertEqual(score, 30 + 12 - 15)
        self.assertEqual([d["kind"] for d in ded], ["invented_fact"])

    def test_field_keeps_course_titles_out_of_software(self):
        for role, want in [("Curriculum Developer", "general"), ("L&D Specialist", "general"), ("Backend Developer", "software"),
                           ("Machine Learning Engineer", "software"), ("Business Development Rep", "general"),
                           ("Data Engineer", "data"), ("Analytics Engineer", "data"), ("Analista de datos", "data"),
                           ("Científico de datos", "data"), ("Desarrollador backend", "software"), ("Diseñador UX", "design")]:
            self.assertEqual(menajer.field({}, role), want, role)

    def test_not_json(self):
        self.assertEqual(menajer.total(None), (None, []))

    def test_letter_form_follows_cv_language(self):
        de = menajer.draft_prompt(JOB, {"cv": {"language": "de"}}, [], [])
        self.assertIn("Write the CV, the letter and the outreach in German", de)
        self.assertIn("Mit freundlichen Grüßen", de)
        self.assertNotIn("Anschreiben", menajer.draft_prompt(JOB, {}, [], []))


class Parse(unittest.TestCase):
    def test_sections_strip_fences(self):
        p = menajer.sections("=== CV ===\n```md\n# A\n```\n=== COVER ===\nletter\n=== OUTREACH ===\n{}")
        self.assertEqual(p, {"CV": "# A", "COVER": "letter", "OUTREACH": "{}"})

    def test_relevant_prefers_matching_and_real_repos(self):
        facts = {"repos": [
            dict(name="todo-app", description="", language="JavaScript", topics=[], stars=0, homepage="", own_commits=12, archived=False),
            dict(name="payapi", description="payment API", language="Python", topics=["postgresql"], stars=3, homepage="", own_commits=40, archived=False),
            dict(name="python-docker-payment", description="", language="Python", topics=[], stars=0, homepage="", own_commits=1, archived=False)]}
        self.assertEqual(menajer.relevant(facts, POSTING, n=1)[0]["name"], "payapi")


class GitHub(unittest.TestCase):
    def test_measures_and_caches(self):
        urls = []

        def get(url):
            urls.append(url)
            if "/users/ada/repos" in url:
                return [dict(name="mine", fork=False, stargazers_count=2, html_url="u"), dict(name="copied", fork=True), dict(name="solo")]
            if "/contributors" in url:
                if "/repos/ada/solo/" in url:
                    return [dict(login="Ada", contributions=3), dict(login="github-actions[bot]", contributions=9, type="Bot")]
                return [dict(login="Ada", contributions=7), dict(login="bob", contributions=1)]
            if "/search/issues" in url:
                return {"items": [dict(repository_url="https://api.github.com/repos/py/cpython", title="fix", html_url="p", closed_at="2026-01-02T0")]}
            raise AssertionError(url)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(menajer, "GH_CACHE", Path(d) / "gh.json"):
            f = menajer.github("ada", get=get)
            self.assertEqual([r["name"] for r in f["repos"]], ["mine", "solo"])
            self.assertEqual((f["repos"][0]["own_commits"], f["repos"][0]["kind"]), (7, "open_source"))
            self.assertEqual(f["repos"][1]["kind"], "self_project")  # a bot is not a second contributor
            self.assertEqual(f["merged_prs_elsewhere"][0]["repo"], "py/cpython")
            n = len(urls)
            menajer.github("ada", get=get)
            self.assertEqual(len(urls), n)  # same day: from the cache


class Run(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for p in [mock.patch.object(menajer, "PACKAGES", Path(self.tmp.name)),
                  mock.patch.object(menajer, "profile", lambda: {"cv": {"language": "en"}, "applicant": {"full_name": "Ada"}}),
                  mock.patch.object(menajer, "apply_py", mock.Mock(return_value=mock.Mock(returncode=0, stdout=""))),
                  mock.patch.object(menajer.subprocess, "run", mock.Mock(return_value=mock.Mock(returncode=0, stdout=""))),
                  mock.patch.object(menajer, "cv_pdf", mock.Mock(return_value=None))]:
            p.start()
            self.addCleanup(p.stop)

    def run_with(self, reviews, fails=(), mail_on=True, guessed_to=False, workers=("claude", "gemini")):
        kos, calls = fake_runner(list(reviews), guessed_to)
        proposals, news = [], []
        self.docs = []
        conf = {**menajer.C, "gateways": {"email": {"enabled": mail_on}}, "agent": {**menajer.C["agent"], "workers": list(workers)}}
        with mock.patch.object(menajer, "cv_check", mock.Mock(side_effect=list(fails) or None, return_value=[])), \
                mock.patch.object(menajer, "C", conf):
            done = menajer.calistir(oneri=lambda m, i, **ek: proposals.append((m, i, ek)), haber=news.append, kos=kos,
                                    jobs=[dict(JOB)], facts={"repos": []}, belge=lambda p, c: self.docs.append((p, c)))
        return done, calls, proposals, news

    def test_low_score_is_revised_once_then_proposed(self):
        done, calls, proposals, news = self.run_with([REVIEW_LOW, REVIEW_HIGH])
        self.assertEqual([c[0] for c in calls], ["[Application package]", "[CV review]", "[CV revision]", "[CV review]"])
        self.assertEqual(done[0]["cv_score"], 90)
        pkg = Path(self.tmp.name) / JOB["id"]
        self.assertIn("40%", (pkg / "cv.md").read_text(encoding="utf-8"))
        self.assertTrue((pkg / "posting.txt").exists())
        self.assertEqual(len(proposals), 2)  # apply + mail
        self.assertIn("mail acme-backend-engineer", proposals[1][1])
        self.assertIn("Hi", proposals[1][0])  # the Yes text shows the whole mail, not a path to it
        self.assertEqual(proposals[1][2]["mail_hash"], menajer.mail_hash({"to": "jobs@acme.io", "subject": "Backend role", "body": "Hi"}))
        for _, task, _ in proposals:  # outside text never reaches the task that runs after Yes
            self.assertNotIn("payment APIs", task)
            self.assertNotIn(JOB["link"], task)
        self.assertIn("CV 90/100", news[0])
        self.assertEqual(len(self.docs), 1)  # no PDF here, so the owner gets cv.md with the proposal
        self.assertEqual(self.docs[0][0], pkg / "cv.md")
        self.assertIn("Acme", self.docs[0][1])
        add = menajer.apply_py.call_args_list[-1].args
        self.assertEqual(add[add.index("--stage") + 1], "drafted")
        out = json.loads((pkg / "outreach.json").read_text(encoding="utf-8"))
        self.assertEqual(out["company"], "Acme")
        rounds = json.loads((pkg / "review.json").read_text(encoding="utf-8"))["rounds"]
        self.assertEqual([r["score"] for r in rounds], [45, 90])

    def test_worse_revision_is_not_kept(self):
        done, _, proposals, _ = self.run_with([REVIEW_HIGH, REVIEW_LOW], fails=[["FAIL x"], ["FAIL x"]])
        self.assertEqual(done[0]["cv_score"], 90)
        self.assertNotIn("40%", (Path(self.tmp.name) / JOB["id"] / "cv.md").read_text(encoding="utf-8"))
        self.assertIn("⚠", proposals[0][0])  # a checker FAIL is flagged in the question

    def test_nested_outreach_keys_lifted(self):
        def kos(prompt, model=None, cli=None, araclar=True):
            if prompt.startswith("[Application package]"):
                out = {"email": {"to": "jobs@acme.io", "subject": "s", "body": "b", "linkedin_note": "note!"}}
                return {"result": f"=== CV ===\n# Ada\n=== COVER ===\nx\n=== OUTREACH ===\n{json.dumps(out)}"}
            return {"result": json.dumps(REVIEW_HIGH)}
        with mock.patch.object(menajer, "cv_check", return_value=[]):
            done = menajer.calistir(haber=lambda m: None, kos=kos, jobs=[dict(JOB)], facts={})
        self.assertEqual(done[0]["note"], "note!")
        self.assertNotIn("linkedin_note", done[0]["mail"])

    def test_posting_text_stays_out_of_files_code_reads_and_the_news(self):
        def kos(prompt, model=None, cli=None, araclar=True):
            if prompt.startswith("[Application package]") and "Broken" in prompt:
                return {"result": "EVIL3", "is_error": True}
            if prompt.startswith("[Application package]"):
                out = {"email": {"to": "jobs@acme.io", "subject": "s", "body": "b"}, "sent_on": "EVIL1", "who_to_contact": "EVIL2"}
                return {"result": f"=== CV ===\n# Ada\n=== COVER ===\nx\n=== OUTREACH ===\n{json.dumps(out)}"}
            return {"result": json.dumps(dict(REVIEW_HIGH, gaps=["EVIL4"]))}
        news, proposals = [], []
        with mock.patch.object(menajer, "cv_check", return_value=[]):
            menajer.calistir(oneri=lambda m, i, **ek: proposals.append(m), haber=news.append, kos=kos, facts={},
                             jobs=[dict(JOB), dict(JOB, id="broken-x", company="Broken")])
        out = json.loads((Path(self.tmp.name) / JOB["id"] / "outreach.json").read_text(encoding="utf-8"))
        self.assertNotIn("sent_on", out)
        self.assertNotIn("EVIL", news[0])
        self.assertIn("EVIL4", proposals[0])  # the gaps still reach the owner, in the question only

    def test_same_or_empty_ids_get_unique_ones(self):
        jobs = menajer.unique_ids([dict(JOB), dict(JOB, link="https://acme.io/j/2"), dict(JOB, id="", link="x")])
        ids = [j["id"] for j in jobs]
        self.assertEqual(len(set(ids)), 3)
        self.assertTrue(all(ids))

    def test_good_first_draft_is_not_revised(self):
        _, calls, _, _ = self.run_with([REVIEW_HIGH])
        self.assertEqual(len(calls), 2)

    def test_one_model_writing_and_scoring_is_said(self):
        done, _, _, _ = self.run_with([REVIEW_HIGH], workers=["claude"])
        review = json.loads((Path(self.tmp.name) / JOB["id"] / "review.json").read_text(encoding="utf-8"))
        self.assertTrue(review["same_model"])
        self.assertTrue("same model" in done[0]["status"] or "aynı model" in done[0]["status"])
        done, _, _, _ = self.run_with([REVIEW_HIGH])
        self.assertNotIn("same model", done[0]["status"])
        self.assertNotIn("aynı model", done[0]["status"])

    def test_checker_fail_forces_a_revision(self):
        _, calls, _, _ = self.run_with([REVIEW_HIGH, REVIEW_HIGH], fails=[["FAIL no numbers"], []])
        self.assertIn("[CV revision]", [c[0] for c in calls])

    def test_guessed_address_dropped_and_no_mail_proposal(self):
        done, _, proposals, _ = self.run_with([REVIEW_HIGH], guessed_to=True)
        self.assertEqual(done[0]["mail"]["to"], "")
        self.assertEqual(len(proposals), 1)

    def test_gateway_off_no_mail_proposal(self):
        _, _, proposals, _ = self.run_with([REVIEW_HIGH], mail_on=False)
        self.assertEqual(len(proposals), 1)

    def test_proposal_names_the_pdf_and_shows_the_note(self):
        _, _, proposals, _ = self.run_with([REVIEW_HIGH])
        self.assertIn("cv.md", proposals[0][1])
        self.assertIn("ask", proposals[0][1])  # no PDF here: the apply run asks instead of guessing
        menajer.cv_pdf.return_value = Path("cv.pdf")
        _, _, proposals, _ = self.run_with([REVIEW_HIGH])
        self.assertIn("cv.pdf", proposals[0][1])
        self.assertRegex(proposals[0][0], r"LinkedIn (note|notu).*\nHi$")

    def test_cv_page_is_plain_and_escaped(self):
        page = menajer.cv_html("# Ada\n## Experience\n**Dev, Acme**\n- Wrote <script>x</script> & [repo](https://github.com/a/b)\n\nPython")
        self.assertIn("<h2>Experience</h2>", page)
        self.assertIn("<b>Dev, Acme</b>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("<script>", page)
        self.assertIn('<a href="https://github.com/a/b">repo</a>', page)
        self.assertEqual(page.count("<ul>"), page.count("</ul>"))
        self.assertNotIn("href", menajer.cv_html("[x](javascript:alert(1))"))  # only http(s) becomes a link

    def test_single_asterisks_become_italics_not_literal_stars(self):
        page = menajer.cv_html("*B.S. in Math, 2027*\n*Acme Corp*\n- Cut build time 4x * 2 runs\n")
        self.assertIn("<i>B.S. in Math, 2027</i>", page)
        self.assertIn("<i>Acme Corp</i>", page)
        self.assertNotIn("*B.S.", page)
        self.assertIn("4x * 2 runs", page)  # a lone star in a sentence stays a star

    def test_one_broken_posting_does_not_stop_others(self):
        kos, _ = fake_runner([REVIEW_HIGH])
        def flaky(prompt, model=None, cli=None, araclar=True):
            if "Broken" in prompt and prompt.startswith("[Application package]"):
                return {"result": "rate limited", "is_error": True}
            return kos(prompt, model, cli, araclar)
        news = []
        with mock.patch.object(menajer, "cv_check", return_value=[]):
            done = menajer.calistir(haber=news.append, kos=flaky, facts={},
                                    jobs=[dict(JOB), dict(JOB, id="broken-x", company="Broken")])
        self.assertEqual(sorted(bool(d.get("error")) for d in done), [False, True])
        self.assertIn("1/2", news[0])


class Mail(unittest.TestCase):
    MAIL = {"to": "jobs@acme.io", "subject": "s", "body": "b"}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        for p in [mock.patch.object(menajer, "PACKAGES", d), mock.patch.object(menajer.subprocess, "run")]:
            self.run_mock = p.start()
            self.addCleanup(p.stop)
        self.pkg, self.onay = d / "acme-x", d / "onaylar.json"
        self.pkg.mkdir()
        (self.pkg / "posting.txt").write_text(f"Acme · Dev\nhttps://acme.io/j\n\n{POSTING}", encoding="utf-8")
        self.sent = []

    def write(self, mail, approved_mail=None, durum="evet"):
        (self.pkg / "outreach.json").write_text(json.dumps({"email": mail, "company": "Acme"}), encoding="utf-8")
        h = menajer.mail_hash(approved_mail or mail)
        self.onay.write_text(json.dumps([{"id": 1, "is": 'Run `"py" -I "menajer.py" mail acme-x` and report', "durum": durum,
                                           "mail_hash": h}]), encoding="utf-8")

    def send(self):
        return menajer.mail("acme-x", send=lambda *a: self.sent.append(a), onaylar_path=self.onay)

    def test_sends_once(self):
        self.write(dict(self.MAIL, to=""))
        self.assertIn("nothing sent", self.send())
        self.write(self.MAIL)
        self.assertIn("sent to jobs@acme.io", self.send())
        self.assertIn("already sent", self.send())
        self.assertEqual(self.sent, [("jobs@acme.io", "s", "b")])
        self.assertIn("network", self.run_mock.call_args.args[0])
        self.assertIn("Acme", self.run_mock.call_args.args[0])  # company from outreach.json, not split from the id

    def test_needs_yes_on_this_exact_text(self):
        self.write(self.MAIL, durum="bekliyor")
        self.assertIn("no approved proposal", self.send())
        self.write(dict(self.MAIL, body="changed after the Yes"), approved_mail=self.MAIL)
        self.assertIn("no approved proposal", self.send())
        self.assertEqual(self.sent, [])

    def test_address_must_be_in_posting_on_company_domain(self):
        for to in ["boss@acme.io", "jobs@acme.io, x@evil.com", "jobs@evil.com"]:
            self.write(dict(self.MAIL, to=to))
            self.assertIn("nothing sent", self.send(), to)
        self.assertEqual(self.sent, [])
        self.assertFalse(menajer.address_ok("hr@gmail.com", dict(company="Acme", link="", text="mail hr@gmail.com")))
        self.assertTrue(menajer.address_ok("jobs@acme.io", dict(company="Acme", link="", text=POSTING)))
        ok = lambda to, company="Foo", link="": menajer.address_ok(to, dict(company=company, link=link, text=f"write {to}"))
        self.assertFalse(ok("x@evil.co.uk", link="https://foo.co.uk/j"))  # same public suffix is not the same site
        self.assertTrue(ok("hr@foo.co.uk", link="https://jobs.foo.co.uk/j"))
        self.assertFalse(ok("hr@acme-careers.net", company="Acme"))
        self.assertTrue(ok("hr@jobs.acme.de", company="Acme"))
        self.assertFalse(ok("me@gmail.com", company="Gmail"))

    def test_lock_stops_a_second_send_and_failure_frees_it(self):
        self.write(self.MAIL)
        (self.pkg / "sent.lock").touch()
        self.assertIn("already", self.send())
        (self.pkg / "sent.lock").unlink()

        def boom(*a):
            raise OSError("smtp down")
        with self.assertRaises(OSError):
            menajer.mail("acme-x", send=boom, onaylar_path=self.onay)
        self.assertFalse((self.pkg / "sent.lock").exists())
        self.assertIn("sent to", self.send())

    def test_bad_id(self):
        self.assertIn("bad id", menajer.mail("../x", onaylar_path=self.onay))


class NoTools(unittest.TestCase):
    def test_claude_gets_no_tools_and_opencode_refuses(self):
        import alt
        with mock.patch.object(alt.subprocess, "run", return_value=mock.Mock(stdout='{"result": "ok"}')) as run, \
                mock.patch.object(alt.agents, "exe", return_value="claude"):
            alt.tek("posting", cli="claude", araclar=False)
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[cmd.index("--tools") + 1], "")
        self.assertIn("--strict-mcp-config", cmd)
        self.assertNotIn("--add-dir", cmd)
        self.assertNotIn("--allowedTools", cmd)
        self.assertTrue(alt.tek("posting", cli="opencode", araclar=False)["is_error"])


if __name__ == "__main__":
    unittest.main()
