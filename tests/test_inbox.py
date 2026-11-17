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
        self.assertNotIn("waiting for evidence", loop_lib.morning("", "quiet: x", "2026-11-10", "/kit", str(self.c)))

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


if __name__ == "__main__":
    unittest.main()
