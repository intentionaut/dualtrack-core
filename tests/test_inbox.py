"""The inbox: every option and bet with its status, read only from the records the loop already keeps."""
import json
import pathlib
import sys
import unittest

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
import loop_lib
try:
    import scratch
except ImportError:  # run as tests.test_x from the repo root
    from tests import scratch


class Inbox(unittest.TestCase):
    def setUp(self):
        self.c = pathlib.Path(scratch.mkdtemp())

    def rows(self):
        text = loop_lib.inbox(str(self.c))
        # Item -> [Status, Since, Detail, Why, Type, Priority]
        return {l.split("|")[1].strip(): [x.strip() for x in l.split("|")[4:8]] + [x.strip() for x in l.split("|")[2:4]]
                for l in text.splitlines() if l.startswith("| ") and not l.startswith("| Item")}

    def test_empty_context_says_so(self):
        self.assertIn("Nothing yet", loop_lib.inbox(str(self.c)))

    def test_every_status_from_the_records(self):
        (self.c / "options.json").write_text(json.dumps({"date": "2026-11-05", "options": [
            {"change": "Fix the crop error", "reason": "", "expected": ""},
            {"change": "Email old users", "reason": "", "expected": ""}]}))
        (self.c / "bets.md").write_text(
            "- 2026-11-01 | Fix the crop error | confirmed by owner\n"
            "- 2026-11-01 | Fix the crop error | started: https://github.com/o/r/pull/7\n"
            "- 2026-11-02 | Rewrite setup | confirmed by owner\n"
            "- 2026-11-02 | Rewrite setup | started: blocked\n"
            "- 2026-11-03 | Add a pricing page | confirmed by owner\n"
            "- 2026-11-03 | Add a pricing page | started: held\n"
            "- 2026-11-04 | Shorter onboarding | started: https://github.com/o/r/pull/8\n"
            "- 2026-11-05 | A DESIGN.md page | confirmed by owner\n")
        (self.c / "decisions.md").write_text(
            "- 2026-11-04 | #7 Unknown crop returns None | yes: merged\n"
            "- 2026-11-05 | #8 Shorter onboarding | no: wrong flow\n"
            "- 2026-11-05 | Email old users | rejected by owner: not now\n")
        r = self.rows()
        self.assertEqual(r["Fix the crop error"][:2], ["Shipped, awaiting evidence", "2026-11-04"])
        self.assertEqual(r["Rewrite setup"][0], "Blocked")
        self.assertEqual(r["Add a pricing page"][0], "Held")
        self.assertEqual(r["Shorter onboarding"][:3:2], ["Closed", "wrong flow"])
        self.assertEqual(r["A DESIGN.md page"][0], "Picked")
        self.assertEqual(r["Email old users"][:3:2], ["Declined", "not now"])

    def test_a_merged_bet_waits_for_evidence_until_a_result_says_what_happened(self):
        (self.c / "bets.md").write_text(
            "- 2026-11-01 | Fix the crop error | expected: crop errors down 50% | read by 2026-11-08 | kill: no change | guardrails: sign-ups not down | baseline: 40 a week, Sentry\n"
            "- 2026-11-01 | Fix the crop error | started: https://github.com/o/r/pull/7\n"
            "- 2026-11-02 | Shorter onboarding | started: https://github.com/o/r/pull/8\n"
            "- 2026-11-03 | Better emails | started: https://github.com/o/r/pull/9\n"
            "- 2026-11-09 | Better emails | result: replies up from 3 to 5\n")
        (self.c / "decisions.md").write_text("- 2026-11-02 | #7 crop | yes: merged\n- 2026-11-03 | #8 onboarding | yes: merged\n"
                                             "- 2026-11-04 | #9 emails | yes: merged\n")
        r = self.rows()
        self.assertEqual(r["Fix the crop error"][0], "Shipped, awaiting evidence")
        self.assertIn("outcome: crop errors down 50%; guardrails: sign-ups not down; window ends 2026-11-08", r["Fix the crop error"][2])
        self.assertEqual(r["Better emails"][:3:2], ["Evidence in", "replies up from 3 to 5"])
        o = loop_lib.outcomes(str(self.c))
        self.assertEqual(o["fix the crop error"]["baseline"], "40 a week, Sentry")
        self.assertEqual([x["title"] for x in loop_lib.overdue(str(self.c), "2026-11-09")], ["Fix the crop error"])
        self.assertEqual(loop_lib.overdue(str(self.c), "2026-11-07"), [])
        with open(self.c / "bets.md", "a") as f:
            f.write("- 2026-11-10 | Fix the crop error | result: helped: 18 a week in Sentry\n")
        self.assertEqual(self.rows()["Fix the crop error"][:3:2], ["Helped", "outcome: crop errors down 50%; guardrails: sign-ups not down; window ends 2026-11-08; 18 a week in Sentry"])
        self.assertEqual(loop_lib.overdue(str(self.c), "2026-11-09"), [])

    def test_a_memo_filed_plan_line_still_sets_the_read_by_date(self):
        # The PM files its expected line with a memo link; the read must still come due. A memo-filed started line is not owner state.
        (self.c / "bets.md").write_text(
            "- 2026-11-03 | Add a call button | expected: 1 booking in 14 days | read by 2026-11-17 | kill: none | baseline: 0, form | memos/2026-11-03-weekly.md\n"
            "- 2026-11-04 | Add a call button | started: https://github.com/o/r/pull/7\n"
            "- 2026-11-04 | Other bet | started: https://github.com/o/r/pull/8 | memos/2026-11-04-weekly.md\n")
        (self.c / "decisions.md").write_text("- 2026-11-05 | #7 button | yes: merged\n- 2026-11-05 | #8 other | yes: merged\n")
        o = loop_lib.outcomes(str(self.c))
        self.assertEqual(list(o), ["add a call button"])
        self.assertEqual((o["add a call button"]["read_by"], o["add a call button"]["baseline"]), ("2026-11-17", "0, form"))
        self.assertEqual([x["title"] for x in loop_lib.overdue(str(self.c), "2026-11-17")], ["Add a call button"])

    def test_mondays_brief_lists_shipped_bets_past_their_read_by_date(self):
        (self.c / "bets.md").write_text("- 2026-11-01 | Fix it | expected: fewer errors | read by 2026-11-08 | kill: none\n"
                                        "- 2026-11-01 | Fix it | started: https://github.com/o/r/pull/7\n")
        (self.c / "decisions.md").write_text("- 2026-11-02 | #7 fix | yes: merged\n")
        monday = loop_lib.morning("", "quiet: x", "2026-11-09", "/kit", str(self.c))
        self.assertIn("## Shipped, waiting for evidence", monday)
        self.assertIn('`python3 /kit/scripts/decide.py result "Fix it" helped|no|unclear "evidence"`', monday)
        self.assertNotIn("waiting for evidence", loop_lib.morning("", "quiet: x", "2026-11-07", "/kit", str(self.c)))  # before the read date

    def test_the_brief_asks_on_the_due_day_and_every_day_after_until_a_result_is_recorded(self):
        (self.c / "bets.md").write_text("- 2026-11-01 | Fix it | expected: fewer errors | read by 2026-11-10 | kill: none\n"
                                        "- 2026-11-01 | Fix it | started: https://github.com/o/r/pull/7\n")
        (self.c / "decisions.md").write_text("- 2026-11-02 | #7 fix | yes: merged\n")
        for day in ("2026-11-10", "2026-11-11", "2026-11-14"):  # Tuesday, Wednesday, Saturday
            self.assertIn("## Shipped, waiting for evidence", loop_lib.morning("", "quiet: x", day, "/kit", str(self.c)), day)
        # A result line an agent filed (it ends in a memo link) is not the owner's call: the question stays.
        with open(self.c / "bets.md", "a") as f:
            f.write("- 2026-11-10 | Fix it | result: helped: up 3 | memos/2026-11-10-weekly.md\n")
        self.assertIn("## Shipped, waiting for evidence", loop_lib.morning("", "quiet: x", "2026-11-11", "/kit", str(self.c)))
        with open(self.c / "bets.md", "a") as f:
            f.write("- 2026-11-11 | Fix it | result: helped: errors halved\n")
        self.assertNotIn("waiting for evidence", loop_lib.morning("", "quiet: x", "2026-11-12", "/kit", str(self.c)))

    def test_the_watch_steps_reading_shows_as_a_draft_beside_the_result_command_and_never_counts(self):
        (self.c / "bets.md").write_text("- 2026-11-01 | Fix it | expected: fewer errors | read by 2026-11-10 | kill: none\n"
                                        "- 2026-11-01 | Fix it | started: https://github.com/o/r/pull/7\n")
        (self.c / "decisions.md").write_text("- 2026-11-02 | #7 fix | yes: merged\n")
        (self.c / "signal.md").write_text("Product manager watch: changed\nErrors fell from 40 to 12 a week.\n")
        out = loop_lib.morning("", "quiet: x", "2026-11-10", "/kit", str(self.c))
        self.assertIn("The watch step's reading: Product manager watch: changed Errors fell from 40 to 12 a week.\nAgree? Record it with the result command below.", out)
        self.assertIn("decide.py result", out)
        self.assertEqual(loop_lib.outcomes(str(self.c))["fix it"]["status"], "Shipped, awaiting evidence")  # a draft is not a result
        (self.c / "signal.md").write_text("")
        self.assertNotIn("The watch step's reading", loop_lib.morning("", "quiet: x", "2026-11-10", "/kit", str(self.c)))

    def test_an_open_pr_and_an_offer_say_what_to_do(self):
        (self.c / "options.json").write_text(json.dumps({"date": "2026-11-05", "options": [
            {"change": "Fix it", "reason": "", "expected": ""}, {"change": "Reach them", "reason": "", "expected": ""}]}))
        (self.c / "bets.md").write_text("- 2026-11-05 | Fix it | started: https://github.com/o/r/pull/9\n")
        text = loop_lib.inbox(str(self.c), "/kit")
        self.assertIn("| Fix it |  |  | PR open | 2026-11-05 | https://github.com/o/r/pull/9 | [bets.md:1](bets.md?plain=1#L1) | Merge it", text)
        self.assertIn("`python3 /kit/scripts/decide.py 2`", text)

    def test_type_priority_resolved_and_why_links(self):
        (self.c / "options.json").write_text(json.dumps({"date": "2026-11-05", "options": [
            {"change": "Fix the crop error", "type": "Issue", "priority": "High", "reason": "", "expected": ""}]}))
        (self.c / "bets.md").write_text(
            "- 2026-11-01 | Explain pricing | confirmed by owner | Insight, Low\n"
            "- 2026-11-02 | Explain pricing | started: resolved: answered in the FAQ\n")
        (self.c / "decisions.md").write_text("- 2026-11-03 | Fix the crop error | rejected by owner: later\n")
        r = self.rows()
        self.assertEqual(r["Explain pricing"], ["Resolved", "2026-11-02", "answered in the FAQ", "[bets.md:2](bets.md?plain=1#L2)", "Insight", "Low"])
        self.assertEqual(r["Fix the crop error"], ["Declined", "2026-11-03", "later", "[decisions.md:1](decisions.md?plain=1#L1)", "Issue", "High"])

    def test_the_command_writes_inbox_md(self):
        self.assertEqual(loop_lib.main(["inbox", str(self.c)]) or 0, 0)
        self.assertTrue((self.c / "inbox.md").read_text().startswith("# Inbox"))


class ReadbackComparison(unittest.TestCase):
    def setUp(self):
        self.c = pathlib.Path(scratch.mkdtemp())
        self.plan = "- 2026-11-01 | Fix it | expected: fewer errors | read by 2026-11-15 | kill: none | baseline: 40, Sentry%s\n"
        (self.c / "bets.md").write_text("- 2026-11-01 | Fix it | started: https://github.com/o/r/pull/7\n")
        (self.c / "decisions.md").write_text("- 2026-11-02 | #7 fix | yes: merged\n- 2026-11-05 | #8 new footer | yes: merged\n"
                                             "- 2026-11-01 | #6 before | yes: merged\n- 2026-11-20 | #9 after | yes: merged\n")

    def plan_with(self, extra):
        with open(self.c / "bets.md", "a") as f:
            f.write(self.plan % extra)

    def test_a_comparison_group_reads_back_both_numbers(self):
        self.plan_with(" | compare: pages the fix did not touch")
        said = loop_lib.compare_readback(str(self.c), "Fix it", "2026-11-15", (40, 20, 30, 30))
        self.assertIn("Bet: 40 to 20. Comparison (pages the fix did not touch): 30 to 30.", said)
        self.assertIn("Comparison stayed flat", said)

    def test_a_comparison_that_moved_too_says_so(self):
        self.plan_with(" | compare: other pages")
        said = loop_lib.compare_readback(str(self.c), "Fix it", "2026-11-15", (40, 20, 30, 18))
        self.assertIn("Comparison moved too", said); self.assertNotIn("stayed flat", said)

    def test_another_merged_change_in_the_window_is_listed(self):
        self.plan_with(" | compare: other pages")
        said = loop_lib.compare_readback(str(self.c), "Fix it", "2026-11-15", (40, 20, 30, 30))
        self.assertIn("Also merged in this window: #8 new footer.", said)
        self.assertNotIn("#6", said); self.assertNotIn("#9", said); self.assertNotIn("#7", said)

    def test_the_due_day_brief_lists_other_merged_changes(self):
        self.plan_with("")
        brief = loop_lib.morning("", "waiting", "2026-11-15", "/kit", str(self.c))
        self.assertIn("Also merged in this window: #8 new footer.", brief)
        self.assertIn("No comparison group named: this shows timing, not cause.", brief)

    def test_the_due_day_brief_reads_the_comparison_numbers_from_the_watch_step(self):
        self.plan_with(" | compare: other pages")
        (self.c / "signal.md").write_text("Comparisons:\n- Other bet | 1 | 2 | 3 | 4\n- Fix it | 40 | 20 | 30 | 30.0\n")
        brief = loop_lib.morning("", "waiting", "2026-11-15", "/kit", str(self.c))
        self.assertIn("Bet: 40 to 20. Comparison (other pages): 30 to 30.", brief)
        self.assertIn("Comparison stayed flat", brief)

    def test_unreadable_comparison_numbers_are_never_guessed(self):
        self.plan_with(" | compare: other pages")
        (self.c / "signal.md").write_text("Comparisons:\n- Fix it | 40 | unknown | 30 | 30\n")
        brief = loop_lib.morning("", "waiting", "2026-11-15", "/kit", str(self.c))
        self.assertIn("no numbers read yet", brief); self.assertNotIn("stayed flat", brief)

    def test_no_comparison_group_says_so_and_never_claims_cause(self):
        self.plan_with("")
        said = loop_lib.compare_readback(str(self.c), "Fix it", "2026-11-15", (40, 20, 30, 30))
        self.assertIn("No comparison group named: this shows timing, not cause.", said)
        self.assertNotIn("likelier cause", said); self.assertNotIn("Comparison stayed", said)


if __name__ == "__main__":
    unittest.main()
