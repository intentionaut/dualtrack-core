"""stats.py: counts the record, and leaks nothing from it."""
import os
import pathlib
import sys
import unittest

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
import stats
try:
    import scratch
except ImportError:  # run as tests.test_x from the repo root
    from tests import scratch

LOG = """# Team log

- 2026-11-01 | quiet: nothing fired | $0.0400
- 2026-11-02 | opened: Fix the secret checkout bug, https://github.invalid/o/r/pull/1, navigator CHANGES APPROVE ux APPROVE  | $1.5000
- 2026-11-03 | opened: Tidy the Acme pricing tests, https://github.invalid/o/r/pull/2, navigator APPROVE ux  | $1.2000
- 2026-11-04 | waiting for the owner's pick: Redesign Acme home | $1.1000
- 2026-11-05 | stopped: the engineer run failed | $0.3000
"""
DECISIONS = """- 2026-11-03 | #1 Fix the secret checkout bug | yes: merged
- 2026-11-04 | #2 Tidy the Acme pricing tests | no: wrong file, private reason here
- 2026-11-04 | Redesign Acme home | rejected by owner: not this quarter
- 2026-11-04 | owner answer to: Who buys? | Acme's CFO
"""


class Stats(unittest.TestCase):
    def test_counts_runs_changes_and_review(self):
        s = stats.stats(LOG, DECISIONS)
        self.assertEqual((s["runs"], s["opened"], s["merged"], s["closed"], s["open"]), (5, 2, 1, 1, 0))
        self.assertEqual(s["caught"], 1)
        self.assertEqual((s["declined"], s["answered"]), (1, 1))
        self.assertEqual(s["kinds"]["a step failed"], 1)
        self.assertAlmostEqual(s["cost_total"], 4.14)

    def test_code_review_and_auto_merge_lines_still_count(self):
        log = LOG + ("- 2026-11-06 | opened: T, https://github.invalid/o/r/pull/3, navigator APPROVE ux code review CHANGES, left for the owner: x | $1.0000\n"
                     "- 2026-11-07 | merged: T, https://github.invalid/o/r/pull/4, commit " + "a" * 40 + ", navigator CHANGES APPROVE ux APPROVE code review APPROVE, plugins none. To undo: git revert x | $1.0000\n")
        s = stats.stats(log, DECISIONS + "- 2026-11-08 | #4 T | yes: merged\n")
        self.assertEqual((s["opened"], s["merged"], s["auto_merged"], s["open"], s["caught"]), (4, 1, 1, 1, 2))
        self.assertEqual(s["kinds"]["built and merged a small change itself"], 1)
        self.assertIn("merged by Dualtrack agents", stats.report(s, 0))

    def test_report_shares_counts_and_nothing_from_the_record(self):
        text = stats.report(stats.stats(LOG, DECISIONS), 2)
        for private in ("Acme", "secret", "checkout", "github", "pull/", "CFO", "private reason", "not this quarter"):
            self.assertNotIn(private, text)
        self.assertIn("approved by the reviewers, then closed by you", text)

    def test_no_runs_says_what_to_do(self):
        self.assertIn("Run Dualtrack once", stats.report(stats.stats("", ""), 0))

    def test_runs_from_the_owner_folder(self):
        d = scratch.mkdtemp(); cwd = os.getcwd()
        try:
            os.chdir(d); os.mkdir("ctx")
            pathlib.Path("profile.md").write_text("**Context path:** ctx\n")
            pathlib.Path("ctx/team-log.md").write_text(LOG)
            self.assertEqual(stats.main(), 0)
        finally:
            os.chdir(cwd)


class Share(unittest.TestCase):
    def test_issue_and_email_links_carry_the_report(self):
        url = stats.share_url("issue", "https://github.invalid/o/kit/issues", "3 runs\n1 merged")
        self.assertTrue(url.startswith("https://github.invalid/o/kit/issues/new?"))
        self.assertIn("3+runs%0A1+merged", url)
        mail = stats.share_url("email", "kit@example.invalid", "3 runs")
        self.assertTrue(mail.startswith("mailto:kit@example.invalid?subject=Dualtrack%20stats"))
        self.assertIn("body=3%20runs", mail)

    def test_never_asks_outside_a_terminal(self):
        self.assertIsNone(stats.choose({"issue": "x"}))

    def test_share_opens_only_the_chosen_destination(self):
        opened = []
        d = scratch.mkdtemp(); cwd = os.getcwd()
        real_open, real_dest = stats.webbrowser.open, stats.destinations
        try:
            os.chdir(d); os.mkdir("ctx")
            pathlib.Path("profile.md").write_text("**Context path:** ctx\n")
            pathlib.Path("ctx/team-log.md").write_text(LOG)
            stats.webbrowser.open = lambda u: opened.append(u) or True
            stats.destinations = lambda: {"email": "kit@example.invalid"}
            self.assertEqual(stats.main(["--share", "email"]), 0)
            self.assertEqual(stats.main(["--share", "issue"]), 2)
            self.assertEqual(stats.main([]), 0)
        finally:
            stats.webbrowser.open, stats.destinations = real_open, real_dest
            os.chdir(cwd)
        self.assertEqual(len(opened), 1); self.assertTrue(opened[0].startswith("mailto:"))
        self.assertNotIn("Acme", opened[0])
