"""Locked areas and the safety card (INT-241), and checks that were out of date (INT-242)."""
import os
import pathlib
import re
import subprocess
import sys
import unittest

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
import safety_card as sc  # noqa: E402
try:
    import scratch
except ImportError:  # run as tests.test_x from the repo root
    from tests import scratch

FILES = ["src/checkout/cart.py", "src/payments/charge.py", "src/auth/login.py", "src/mail/welcome_email.py",
         "src/pages/pricing.astro", "src/pages/about.astro", "tests/test_checkout.py", "README.md"]
PROFILE = "# Product profile\n\n**Mode:** acquisition\n\n**Auto-merge:** off\n"


def card(**kw):
    base = {"title": "Shorter sign-up form", "outcome": "raise sign-ups", "mode": "ask", "checks": [], "skipped": [], "guardrails": "", "stop": ""}
    return {**base, **kw}


def check(**kw):
    return {"name": "Sign-up still works, start to finish", "why": "We filled in the form the way a customer would.",
            "tests": ["tests/test_signup.py"], "result": "passed", **kw}


class Locked(unittest.TestCase):
    def test_setup_suggests_areas_from_the_files_and_names_the_files(self):
        found = {name: files for name, _, files in sc.suggest(FILES)}
        self.assertEqual(list(found), ["Payments and checkout", "Login and accounts", "Emails to customers", "Pricing page"])
        self.assertIn("src/checkout/cart.py", found["Payments and checkout"])
        self.assertNotIn("tests/test_checkout.py", found["Payments and checkout"])  # a test is not the area
        self.assertEqual(sc.suggest(["README.md"]), [])

    def test_the_choice_is_saved_and_read_back(self):
        picks = [(n, rx) for n, rx, _ in sc.suggest(FILES)][:2]
        saved = sc.save(PROFILE, picks)
        self.assertEqual(sc.locked(saved), picks)
        self.assertIn("**Mode:** acquisition", saved)
        # Saving again replaces the list; it never doubles it.
        self.assertEqual(sc.locked(sc.save(saved, picks[:1])), picks[:1])
        self.assertEqual(sc.locked(sc.save(saved, [])), [])

    def test_a_run_that_touches_a_locked_area_stops_with_a_plain_message_and_three_choices(self):
        saved = sc.save(PROFILE, [(n, rx) for n, rx, _ in sc.suggest(FILES)])
        hit = sc.touched(saved, ["src/pages/about.astro", "src/auth/login.py"])
        self.assertEqual(hit[0], "Login and accounts")
        msg = sc.stop_message(hit[0], "Shorter sign-up form")
        for line in ("Stopped: this change needs login and accounts", "Nothing was shipped", "Your product is unchanged",
                     "Allow a change to login and accounts, just for this bet", "Find a version that leaves login and accounts alone",
                     "Drop this bet"):
            self.assertIn(line, msg)
        self.assertEqual(len(re.findall(r"^\s*(?:❯ )?(?:Allow|Find|Drop)", msg, re.M)), 3)
        self.assertIsNone(sc.touched(saved, ["src/pages/about.astro", "tests/test_login.py"]))  # tests may change
        self.assertIsNone(sc.touched(PROFILE, ["src/auth/login.py"]))  # nothing locked, nothing stops

    def test_the_setup_card_asks_for_the_owner_choice(self):
        text = sc.setup_card(sc.suggest(FILES))
        for line in ("What should never change without asking?", "Payments and checkout", "Login and accounts", "We found these in your code"):
            self.assertIn(line, text)


class Card(unittest.TestCase):
    def test_passed_stopped_and_not_checked_rows_each_have_one_grey_line(self):
        text = sc.render(card(
            checks=[check(),
                    check(name="Checkout and login untouched", why="They are on your locked list.", result="failed", cause="product",
                          reason="the form lost its email field", fault="dualtrack", fixed=False)],
            skipped=["how it looks on very old phones"]))
        self.assertIn("✓ Sign-up still works, start to finish", text)
        self.assertIn("✕ Stopped: Checkout and login untouched", text)
        self.assertIn("the form lost its email field", text)
        self.assertIn("Our change caused this", text)
        self.assertIn("Your product is unchanged", text)
        self.assertIn("We could not fix it ourselves", text)
        self.assertIn("– Not checked: how it looks on very old phones", text)
        grey = [l for l in text.splitlines() if "↳" in l]
        self.assertIn("   ↳ We filled in the form the way a customer would.", grey)

    def test_a_stop_says_when_dualtrack_fixed_it_itself(self):
        text = sc.render(card(checks=[check(fault="dualtrack", fixed=True, reason="the form lost its email field", result="passed")]))
        self.assertIn("Fixed for you: the form lost its email field", text)
        self.assertIn("✓ Sign-up still works", text)

    def test_the_card_ends_with_one_outcome_question_and_never_mentions_code(self):
        text = sc.render(card(checks=[check()], skipped=["x"]))
        self.assertEqual(text.rstrip().splitlines()[-1].strip(), "Ship it? It should raise sign-ups.")
        self.assertEqual(text.count("?"), 1)
        for word in ("diff", "commit", "patch", "pull request", "assert", "test_"):
            self.assertNotIn(word, text.lower())
        stop = sc.render(card(checks=[check(result="failed", reason="r", fault="product")]))
        self.assertNotIn("diff", stop.lower())
        self.assertEqual(stop.count("?"), 1)

    def test_autonomy_decides_ask_or_record(self):
        self.assertEqual(sc.mode("**Auto-merge:** off\n"), "ask")
        self.assertEqual(sc.mode("**Auto-merge:** on\n"), "record")
        self.assertEqual(sc.mode(""), "ask")
        asked = sc.render(card(mode="ask", checks=[check()]))
        recorded = sc.render(card(mode="record", checks=[check()]))
        self.assertIn("Ship it? It should raise sign-ups.", asked)
        self.assertNotIn("Ship it?", recorded)
        # Auto-merge on does not mean this change merges (size, risky files, company mode): the card does not say it does.
        self.assertIn("Recorded, not asked. Your settings decide what happens next. It should raise sign-ups.", recorded)
        self.assertEqual(sc.mode("**Auto-merge:** on\n\n**Company mode:** on\n"), "ask")
        # A stop always asks: a card never records past a failure.
        stopped = sc.render(card(mode="record", checks=[check(result="failed", reason="r", fault="product")]))
        self.assertIn("What should happen?", stopped)

    def test_no_check_for_a_guardrail_is_said_out_loud(self):
        text = sc.render(card(guardrails="Sign-ups are still being counted", stop="drop below 2 percent", checks=[check()]))
        self.assertIn("Not checked: Sign-ups are still being counted", text)
        self.assertIn("Not checked: drop below 2 percent", text)
        covered = sc.render(card(guardrails="Sign-ups are still being counted", checks=[check(name="Sign-ups are still being counted")]))
        self.assertNotIn("Not checked", covered)


class OutOfDate(unittest.TestCase):
    def test_a_rewritten_check_that_then_passes_is_not_checked_never_passed(self):
        rewritten = {"tests/test_signup.py": ("the form had 5 fields", "the form has 3 fields")}
        text = sc.render(card(checks=[check(was="the form had 5 fields", now="the form has 3 fields")]), rewritten)
        self.assertNotIn("✓ Sign-up still works", text)
        self.assertIn("– Not checked: Sign-up still works, start to finish", text)
        self.assertIn("out of date", text)
        self.assertIn("Approve the new check", text)
        old_new = [l for l in text.splitlines() if "the form had 5" in l and "the form has 3" in l]
        self.assertTrue(old_new, "old and new check read side by side on one line")

    def test_a_check_marked_out_of_date_is_not_checked_even_if_it_still_fails(self):
        text = sc.render(card(checks=[check(result="failed", cause="out of date", reason="it expects 5 fields")]))
        self.assertIn("Not checked: Sign-up still works", text)
        self.assertNotIn("Stopped", text)

    def test_a_real_failure_is_stopped_with_the_reason_in_plain_words(self):
        text = sc.render(card(checks=[check(result="failed", cause="product", reason="the form lost its email field", fault="dualtrack")]))
        self.assertIn("✕ Stopped: Sign-up still works, start to finish", text)
        self.assertIn("the form lost its email field", text)
        self.assertNotIn("✓", text)
        # No cause named: the safe reading is that the product is wrong.
        self.assertIn("Stopped", sc.render(card(checks=[check(result="failed", reason="r")])))

    def test_a_rewrite_never_passes_even_if_the_check_says_it_did_not_change(self):
        # The loop sees the test file lose lines; the engineer's own word does not count.
        text = sc.render(card(checks=[check()]), {"tests/test_signup.py": ("a", "b")})
        self.assertIn("Not checked", text)
        self.assertNotIn("✓", text)

    def test_rewrites_are_read_from_the_branch_not_from_the_report(self):
        t = pathlib.Path(scratch.mkdtemp())
        def git(*a): return subprocess.run(["git", "-C", str(t), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True, text=True).stdout.strip()
        git("init", "-q", "-b", "main")
        (t / "tests").mkdir()
        (t / "tests/test_signup.py").write_text("def test_a():\n    assert fields() == 5\n")
        (t / "tests/test_new.py").write_text("x = 1\n")
        (t / "app.py").write_text("a = 1\n")
        git("add", "-A"); git("commit", "-qm", "base")
        base = git("rev-parse", "HEAD")
        (t / "tests/test_signup.py").write_text("def test_a():\n    assert fields() == 3\n")  # an old check, rewritten
        (t / "tests/test_other.py").write_text("y = 1\n")  # a new test file is not a rewrite
        (t / "app.py").write_text("a = 2\n")  # not a test
        git("add", "-A"); git("commit", "-qm", "work")
        got = sc.rewrites(str(t), base, "HEAD")
        self.assertEqual(list(got), ["tests/test_signup.py"])
        self.assertIn("fields() == 5", got["tests/test_signup.py"][0])
        self.assertIn("fields() == 3", got["tests/test_signup.py"][1])

    def test_a_rewrite_no_check_claims_still_gets_a_not_checked_row_and_paths_are_normalised(self):
        text = sc.render(card(checks=[check(tests=["./tests/test_signup.py::test_a"])]),
                         {"tests/test_signup.py": ("a", "b"), "tests/test_other.py": ("c", "d")})
        self.assertNotIn("✓", text)  # ./path and path::test_name still match the rewritten file
        self.assertIn("1 other check was rewritten in this run", text)
        self.assertIn("Approve the new check", text)
        self.assertEqual(text.count("What changed was not described."), 1)  # the claimed one; the unclaimed row says it once, in its own words

    def test_a_rewrite_without_words_for_old_and_new_says_so_once(self):
        text = sc.render(card(checks=[check()]), {"tests/test_signup.py": ("a", "b")})
        self.assertIn("What changed was not described.", text)
        self.assertNotIn("not described   ", text)

    def test_placeholders_are_not_guardrails(self):
        for g in ("none", "none named", "<one or two numbers>", "Unknown"):
            self.assertNotIn("Not checked", sc.render(card(guardrails=g, stop="none", checks=[check()])))

    def test_when_the_tests_failed_nothing_the_report_claims_counts_as_passed(self):
        text = sc.render(card(tests_failed=True, checks=[check()]))
        self.assertNotIn("✓", text)
        self.assertIn("Stopped: the checks did not all pass", text)
        self.assertIn("What should happen?", text)

    def test_the_owner_question_is_one_line_with_all_three_choices(self):
        q = sc.stop_question("Login and accounts", "Shorter sign-up form")
        self.assertNotIn("\n", q)
        for part in ("login and accounts", "1) Allow a change", "2) Find a version", "3) Drop this bet"):
            self.assertIn(part, q)

    def test_the_merge_gate_never_merges_a_run_that_rewrote_a_check(self):
        self.assertEqual(sc.rewrote(["M\ttests/test_a.py\n", "A\ttests/test_b.py"], ["1\t1\ttests/test_a.py", "9\t0\ttests/test_b.py"]), ["tests/test_a.py"])
        self.assertEqual(sc.rewrote(["M\ttests/test_a.py"], ["4\t0\ttests/test_a.py"]), [])  # only added lines: not a rewrite
        self.assertEqual(sc.rewrote(["M\tsrc/a.py"], ["1\t1\tsrc/a.py"]), [])
        self.assertEqual(sc.rewrote(["D\ttests/test_a.py"], ["0\t5\ttests/test_a.py"]), ["tests/test_a.py"])

    def test_checks_are_read_from_the_engineer_report(self):
        report = ("DONE\n\nChanged: x\nChecks:\n"
                  "- Sign-up still works, start to finish | We filled in the form like a customer. | tests/test_signup.py | passed\n"
                  "- Emails still go out | Customers expect a welcome. | tests/test_mail.py | failed: out of date: it expects 5 fields | was: five fields | now: three fields\n"
                  "- Login works | People get back in. | tests/test_login.py | failed: product: the login button vanished | fault: dualtrack | fixed: no\n"
                  "Skipped: how it looks on very old phones; the print layout\nUnchecked: none\nRisk: low\n")
        got = sc.parse_report(report)
        self.assertEqual([c["result"] for c in got["checks"]], ["passed", "failed", "failed"])
        self.assertEqual(got["checks"][1]["cause"], "out of date")
        self.assertEqual((got["checks"][1]["was"], got["checks"][1]["now"]), ("five fields", "three fields"))
        self.assertEqual(got["checks"][2]["cause"], "product")
        self.assertEqual(got["checks"][2]["reason"], "the login button vanished")
        self.assertEqual(got["checks"][2]["fault"], "dualtrack")
        self.assertEqual(got["skipped"], ["how it looks on very old phones", "the print layout"])
        self.assertEqual(sc.parse_report("DONE\nSkipped: none\n")["skipped"], [])


AREAS_LOGIN = sc.AREAS["Login and accounts"]
TEMPLATE = (KIT / ".github/pull_request_template.md").read_text()


class InTheRun(unittest.TestCase):
    """The loop's own pieces: the card from a run's files, the stop command and the pull request text."""

    def repo(self):
        t = pathlib.Path(scratch.mkdtemp())

        def git(*a):
            return subprocess.run(["git", "-C", str(t), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True, text=True).stdout.strip()
        git("init", "-q", "-b", "main")
        (t / "tests").mkdir()
        (t / "tests/test_signup.py").write_text("assert fields() == 5\n")
        git("add", "-A")
        git("commit", "-qm", "base")
        base = git("rev-parse", "HEAD")
        (t / "tests/test_signup.py").write_text("assert fields() == 3\n")
        git("add", "-A")
        git("commit", "-qm", "work")
        return t, base

    def test_a_run_that_rewrites_a_failing_check_and_then_passes_shows_not_checked(self):
        t, base = self.repo()
        run = pathlib.Path(scratch.mkdtemp())
        (run / "item.json").write_text('{"title": "Shorter sign-up form"}')
        (run / "engineer.txt").write_text("DONE\nChecks:\n- Sign-up still works | We fill the form like a customer. | tests/test_signup.py | passed | was: five fields | now: three fields\nSkipped: none\n")
        text = sc.from_run(str(run), "**Auto-merge:** off\n", str(t), base, "HEAD", str(run))
        self.assertIn("– Not checked: Sign-up still works", text)
        self.assertNotIn("✓", text)
        self.assertIn("five fields", text)
        self.assertIn("three fields", text)

    def test_the_stop_command_and_the_locked_command(self):
        cli = [sys.executable, str(KIT / "scripts/safety_card.py")]
        out = subprocess.run([*cli, "stop", "Login and accounts", "Shorter sign-up form"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0)
        self.assertIn("Drop this bet", out.stdout)
        t = pathlib.Path(scratch.mkdtemp())
        (t / "profile.md").write_text(sc.save(PROFILE, [("Login and accounts", AREAS_LOGIN)]))
        (t / "diff.txt").write_text("M\tsrc/auth/login.py\n")
        hit = subprocess.run([*cli, "locked", str(t / "profile.md"), str(t / "diff.txt"), "Shorter sign-up form"], capture_output=True, text=True)
        self.assertEqual(hit.returncode, 4)
        self.assertIn("Stopped: this change needs login and accounts", hit.stdout)
        (t / "diff.txt").write_text("M\tsrc/pages/about.astro\n")
        miss = subprocess.run([*cli, "locked", str(t / "profile.md"), str(t / "diff.txt"), "x"], capture_output=True, text=True)
        self.assertEqual((miss.returncode, miss.stdout), (0, ""))

    def test_a_locked_stop_reaches_the_brief_with_all_three_choices_and_offers_allow(self):
        import loop_lib
        ask = "\nOwner question:\n%s Recommended: choose 2.\n\nQuestion bet: Shorter sign-up form\n" % sc.stop_question("Login and accounts", "Shorter sign-up form")
        brief = loop_lib.morning("", "held for the owner: it needs a locked area", "2026-11-20", ask=ask)
        for part in ("1) Allow a change to login and accounts, just for this bet", "2) Find a version that leaves login and accounts alone", "3) Drop this bet"):
            self.assertIn(part, brief)
        self.assertEqual(loop_lib.gate("held for the owner: it needs a locked area")["offer"], "allow")

    def test_a_red_branch_card_says_stopped_and_never_passed(self):
        t, base = self.repo()
        run = pathlib.Path(scratch.mkdtemp())
        (run / "item.json").write_text('{"title": "Shorter sign-up form"}')
        (run / "engineer.txt").write_text("DONE\nChecks:\n- Sign-up still works | We fill the form like a customer. | tests/test_x.py | passed\n")
        out = subprocess.run([sys.executable, str(KIT / "scripts/safety_card.py"), "card", str(run), str(run / "none.md"), str(t), base, "HEAD", str(run), "failed"],
                             capture_output=True, text=True)
        self.assertNotEqual(out.returncode, 0)  # an unreadable profile is an error, not a card that passes
        (run / "profile.md").write_text("**Auto-merge:** off\n")
        out = subprocess.run([sys.executable, str(KIT / "scripts/safety_card.py"), "card", str(run), str(run / "profile.md"), str(t), base, "HEAD", str(run), "failed"],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Stopped: the checks did not all pass", out.stdout)
        self.assertNotIn("✓", out.stdout)

    def test_the_card_joins_the_pull_request_text_before_the_trail(self):
        import loop_lib
        item = {k: "x" for k in ("what", "why", "how_to_check", "decision", "watching")}
        facts = {"repo_url": "https://example.test/r", "item": item, "commits": [], "failed_first": "failed", "tests": "passed",
                 "verdicts": [], "card": "⛨ Safety check · T\n ✓ It works"}
        body = loop_lib.trail(facts, TEMPLATE)
        self.assertLess(body.index("## Safety check"), body.index("## How this was made"))
        self.assertIn("✓ It works", body)
        self.assertNotIn("## Safety check", loop_lib.trail({k: v for k, v in facts.items() if k != "card"}, TEMPLATE))


class SetupSaves(unittest.TestCase):
    """setup_apply files the owner's locked areas in the profile: the suggested ones unless the owner says otherwise."""

    def setUp(self):
        self.t = pathlib.Path(scratch.mkdtemp())
        self.repo = self.t / "shop"
        (self.repo / "src/checkout").mkdir(parents=True)
        (self.repo / "src/checkout/cart.py").write_text("x = 1\n")
        (self.repo / "tests").mkdir()
        (self.repo / "tests/__init__.py").write_text("")
        (self.repo / "tests/test_a.py").write_text("import unittest\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        pass\n")
        (self.repo / "setup.md").write_text("# Product profile\n\n**Mode:** acquisition\n\n**Test commands:** `python3 -m unittest discover -s tests -t .`\n")
        for a in (["init", "-q", "-b", "main"], ["add", "."], ["-c", "user.name=t", "-c", "user.email=t@t.invalid", "commit", "-qm", "i"]):
            subprocess.run(["git", "-C", str(self.repo), *a], check=True, capture_output=True)

    def apply(self, *extra):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t.invalid", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t.invalid")
        r = subprocess.run([sys.executable, str(KIT / "scripts/setup_apply.py"), "--record", "local", "--runs", "local", *extra],
                           cwd=self.repo, capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return (self.repo / "profile.md").read_text(), r.stdout

    def test_suggested_areas_are_saved_by_default_and_named_in_the_output(self):
        profile, out = self.apply()
        self.assertEqual([n for n, _ in sc.locked(profile)], ["Payments and checkout"])
        self.assertIn("Locked: Payments and checkout", out)

    def test_the_owner_can_pick_none(self):
        self.assertEqual(sc.locked(self.apply("--locked", "none")[0]), [])

    def test_the_owner_can_pick_by_name_or_add_their_own(self):
        profile, _ = self.apply("--locked", "Pricing page; Our reports :: reports/")
        self.assertEqual(sc.locked(profile)[1], ("Our reports", "reports/"))
        self.assertEqual(sc.locked(profile)[0][0], "Pricing page")


if __name__ == "__main__":
    unittest.main()
