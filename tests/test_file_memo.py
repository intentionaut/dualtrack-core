"""Run: python3 tests/test_file_memo.py"""
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts/file_memo.py"
sys.path.insert(0, str(ROOT / "scripts"))
from file_memo import check_new_ideas
import loop_lib
import status
WEEKLY = """Product manager memo, 2026-01-05: gaps
Mode: acquisition
Cadence: weekly

Recommendation:
Count sign-ups
Verdict: confirmed
Move: Learn
Why: no reversible bet
Score: reach 3, evidence 3, effort 4, goal link 3
Goal link: owners reading the count, who then act on sign-ups
Moves: sign-ups

Bets:
- proposed new idea: a page

New ideas:
- A new page: audience, promise

Record:
- decisions: Count sign-ups | proposed
- gaps: Sign-ups | read the form
- nonsense: ignored
"""
DAILY = "Product manager daily, 2026-01-06: quiet\nCadence: daily\n\nRecommendation:\nnone today\n"


class FileMemo(unittest.TestCase):
    def test_rejected_top_pick_files_nothing(self):
        r = self.run_it(WEEKLY.replace("Verdict: confirmed", "Verdict: rejected"))
        self.assertEqual(r.returncode, 2); self.assertIn("rejected candidate", r.stdout)

    def test_no_verdict_files_nothing(self):
        self.assertEqual(self.run_it(WEEKLY.replace("Verdict: confirmed\n", "")).returncode, 2)

    def test_a_verdict_word_with_trailing_text_is_read_and_an_unknown_word_still_fails(self):
        self.assertEqual(self.run_it(WEEKLY.replace("Verdict: confirmed", "Verdict: confirmed (with a note)")).returncode, 0)
        r = self.run_it(WEEKLY.replace("Verdict: confirmed", "Verdict: rejected (by the owner)"))
        self.assertEqual(r.returncode, 2); self.assertIn("rejected candidate", r.stdout)
        self.assertEqual(self.run_it(WEEKLY.replace("Verdict: confirmed", "Verdict: maybe (ok)")).returncode, 2)
        self.assertEqual(self.run_it(WEEKLY.replace("Verdict: confirmed", "Verdict: confirmedly")).returncode, 2)

    def test_needs_validation_must_be_stated(self):
        text = WEEKLY.replace("Verdict: confirmed", "Verdict: needs_validation")
        self.assertEqual(self.run_it(text).returncode, 2)
        text = text.replace("Moves: sign-ups", "Why: needs_validation, the count\nMoves: sign-ups")
        self.assertEqual(self.run_it(text).returncode, 0)

    def test_needs_validation_fact_on_the_verdict_line(self):
        # Kept run 2026-11-16: the fact sat on the Verdict line and Why gave only a reason.
        v = "Verdict: needs_validation. The 14-report figure comes from the owner's notes, with no date window."
        text = WEEKLY.replace("Verdict: confirmed", v)
        self.assertEqual(self.run_it(text).returncode, 0)
        self.assertEqual(self.run_it(WEEKLY.replace("Verdict: confirmed", "Verdict: needs_validation.")).returncode, 2)
        self.assertEqual(self.run_it(WEEKLY.replace("Verdict: confirmed", "Verdict: needs_validation (maybe)")).returncode, 2)

    def test_needs_validation_may_name_a_done_when_line(self):
        text = WEEKLY.replace("Verdict: confirmed", "Verdict: needs_validation").replace(
            "Moves: sign-ups", 'Why: needs_validation: done_when "the page feels faster": not observable from outside the code\nMoves: sign-ups')
        self.assertEqual(self.run_it(text).returncode, 0)

    def test_rejected_candidates_are_recorded_and_not_reproposed(self):
        line = "- decisions: Retitle the page | rejected: wrong audience\n"
        self.assertEqual(self.run_it(WEEKLY.replace("- nonsense", line + "- nonsense")).returncode, 0)
        saved = (self.ctx / "decisions.md").read_text()
        self.assertIn("Retitle the page | rejected: wrong audience", saved)
        self.assertNotIn("wrong audience | move", saved)
        again = WEEKLY.replace("Count sign-ups\nVerdict", "Retitle the page\nVerdict")
        r = self.run_it(again.replace("Move: Learn", "Move: Reach"))
        self.assertEqual(r.returncode, 2); self.assertIn("already rejected", r.stdout)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self.tmp.name)
        self.ctx = self.dir / "ctx"

    def tearDown(self):
        self.tmp.cleanup()

    def run_it(self, text, store="local", path=None, mode=""):
        (self.dir / "numbers.md").write_text("n\n")
        profile = self.dir / "profile.md"
        profile.write_text(f"**Numbers file:** {self.dir}/numbers.md\n\n**Context store:** {store}\n\n**Context path:** {path or self.ctx}\n"
                           + (f"\n**Mode:** {mode}\n" if mode else ""))
        msg = self.dir / "msg.md"
        msg.write_text(text)
        return subprocess.run([sys.executable, SCRIPT, profile, msg], capture_output=True, text=True)

    def test_weak_goal_link_cannot_win(self):
        bad = WEEKLY.replace("goal link 3", "goal link 2")
        self.assertEqual(self.run_it(bad).returncode, 2)
        self.assertFalse((self.ctx / "memos").exists())

    def test_a_bet_the_owner_confirmed_in_the_record_beats_the_goal_link(self):
        self.ctx.mkdir()
        (self.ctx / "bets.md").write_text("- 2026-01-04 | Count sign-ups | confirmed by owner\n")
        self.assertEqual(self.run_it(WEEKLY.replace("goal link 3", "goal link 2")).returncode, 0)

    def test_a_confirmed_bet_matches_when_the_memo_shortens_its_title(self):
        self.ctx.mkdir()
        (self.ctx / "bets.md").write_text("- 2026-01-04 | Count sign-ups. Follow the issue's settled decisions. | confirmed by owner\n")
        self.assertEqual(self.run_it(WEEKLY.replace("goal link 3", "goal link 2")).returncode, 0)

    def test_a_different_confirmed_bet_does_not_lift_the_gate(self):
        self.ctx.mkdir()
        (self.ctx / "bets.md").write_text("- 2026-01-04 | Something else | confirmed by owner\n")
        self.assertEqual(self.run_it(WEEKLY.replace("goal link 3", "goal link 2")).returncode, 2)

    def test_two_modes_at_once(self):
        self.assertEqual(self.run_it(WEEKLY, mode="acquisition, optimisation").returncode, 0)
        r = self.run_it(WEEKLY.replace("Mode: acquisition", "Mode: optimisation").replace("Move: Learn", "Move: Reach"), mode="acquisition, optimisation")
        self.assertEqual(r.returncode, 0)

    def test_the_memo_mode_must_be_one_the_profile_lists(self):
        r = self.run_it(WEEKLY.replace("Mode: acquisition", "Mode: activation"), mode="acquisition, optimisation")
        self.assertEqual(r.returncode, 2); self.assertIn("not one of the profile's modes", r.stdout)

    def test_at_most_two_modes(self):
        r = self.run_it(WEEKLY, mode="acquisition, activation, optimisation")
        self.assertEqual(r.returncode, 2); self.assertIn("at most 2 modes", r.stdout)

    def test_a_narration_line_before_the_status_line_is_dropped(self):
        # Real run, 2026-11-12: the agent narrated one line before the memo.
        r = self.run_it("I'm writing up the decide memo. The top pick is checked.\n\n" + WEEKLY)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertEqual((self.ctx / "memos/2026-01-05-weekly.md").read_text(), WEEKLY)

    def test_no_status_line_anywhere_still_files_nothing(self):
        self.assertEqual(self.run_it("I'm writing up the memo.\n" + WEEKLY.split("\n", 1)[1]).returncode, 2)

    def test_the_memo_cannot_confirm_a_bet_for_the_owner(self):
        # Only decide.py records the owner's confirmation; a memo claiming it would skip the goal-link gate.
        for line in ("- bets: Count sign-ups | confirmed by owner", "- bets: X | Confirmed By Owner | why"):
            r = self.run_it(WEEKLY.replace("- nonsense: ignored", line))
            self.assertEqual(r.returncode, 2, line); self.assertIn("only the owner confirms", r.stdout)
        self.assertFalse((self.ctx / "bets.md").exists())

    def forge(self, record, bets="", decisions=""):
        """File a memo whose Record block carries the forged line, over an existing record."""
        self.ctx.mkdir(exist_ok=True)
        (self.ctx / "bets.md").write_text(bets); (self.ctx / "decisions.md").write_text(decisions)
        r = self.run_it(WEEKLY.replace("- nonsense: ignored", record))
        self.assertEqual(r.returncode, 0, r.stdout)
        return (self.ctx / "bets.md").read_text(), (self.ctx / "decisions.md").read_text()

    def test_a_memo_cannot_open_a_bet_as_confirmed(self):
        bets, _ = self.forge("- bets: Forged pick | confirmed")
        self.assertIn("Forged pick | confirmed", bets)  # filed as the memo's note, but it is not an owner pick
        self.assertEqual(loop_lib.open_titles(bets), [])
        self.assertNotIn("forged pick", loop_lib.owners(bets))

    def test_a_memo_cannot_withdraw_the_owners_bet(self):
        bets, _ = self.forge("- bets: Real bet | withdrawn", bets="- 2026-01-01 | Real bet | confirmed by owner\n")
        self.assertEqual(loop_lib.open_titles(bets), ["Real bet"])
        self.assertEqual(loop_lib.withdrawn(bets), set())

    def test_a_memo_cannot_resume_a_pause(self):
        _, decisions = self.forge("- decisions: owner | resume")
        prs = [{"number": n, "title": "t", "state": "CLOSED", "closedAt": f"2026-01-0{n}T00:00:00Z", "mergedAt": None, "comments": []} for n in (1, 2)]
        (self.ctx / "decisions.md").write_text(decisions)
        self.assertEqual(loop_lib.feed(prs, str(self.ctx / "decisions.md")), "pause")

    def test_a_memo_cannot_answer_the_owners_question(self):
        _, decisions = self.forge("- decisions: the page | by owner: yes")
        self.assertFalse(status.answered(str(self.ctx), {"date": "2026-01-01"}))

    def test_goal_link_score_required(self):
        self.assertEqual(self.run_it(WEEKLY.replace(", goal link 3", "")).returncode, 2)

    def test_goal_link_path_required(self):
        self.assertEqual(self.run_it(WEEKLY.replace("Goal link: owners", "Other: owners")).returncode, 2)

    def test_moves_names_a_number(self):
        self.assertEqual(self.run_it(WEEKLY.replace("Moves: sign-ups", "Moves: 2")).returncode, 2)

    def test_local(self):
        self.assertEqual(self.run_it(WEEKLY).returncode, 0)
        self.assertEqual((self.ctx / "memos/2026-01-05-weekly.md").read_text(), WEEKLY)
        self.assertIn("- 2026-01-05 | Sign-ups | read the form | memos/2026-01-05-weekly.md\n", (self.ctx / "gaps.md").read_text())
        self.assertIn("Count sign-ups", (self.ctx / "decisions.md").read_text())
        self.assertFalse((self.ctx / "nonsense.md").exists())
        self.assertTrue((self.ctx / "numbers/2026-01-05.md").exists())

    def test_learn_cannot_win_twice(self):
        self.assertEqual(self.run_it(WEEKLY).returncode, 0)
        self.assertIn("| move: Learn |", (self.ctx / "decisions.md").read_text())
        r = self.run_it(WEEKLY)
        self.assertEqual(r.returncode, 2)
        self.assertIn("Learn cannot win two runs in a row", r.stdout)
        self.assertEqual(len(list((self.ctx / "memos").iterdir())), 1)
        self.assertEqual(self.run_it(WEEKLY.replace("Move: Learn", "Move: Reach")).returncode, 0)
        self.assertEqual(self.run_it(WEEKLY).returncode, 0)

    def test_memo_needs_a_valid_move(self):
        self.assertEqual(self.run_it(WEEKLY.replace("Move: Learn", "Move: Guess")).returncode, 2)
        self.assertEqual(self.run_it(WEEKLY.replace("- decisions: Count sign-ups | proposed\n", "")).returncode, 2)

    def test_daily(self):
        self.assertEqual(self.run_it(DAILY).returncode, 0)
        self.assertTrue((self.ctx / "memos/2026-01-06-daily.md").exists())

    def test_obsidian(self):
        self.assertEqual(self.run_it(WEEKLY, "obsidian").returncode, 0)
        memo = (self.ctx / "memos/2026-01-05-weekly.md").read_text()
        self.assertTrue(memo.startswith("---\ndate: 2026-01-05\ncadence: weekly\nstatus: gaps\n---\n"))
        self.assertIn("[[decisions]]", memo)
        self.assertIn("[[memos/2026-01-05-weekly]]", (self.ctx / "gaps.md").read_text())

    def test_notion_stays_local_and_says_pending(self):
        r = self.run_it(WEEKLY, "notion")
        self.assertEqual(r.returncode, 0)
        self.assertIn("notion: pending", r.stdout)

    def test_too_few_new_ideas(self):
        with self.assertRaises(ValueError) as e:
            check_new_ideas("Move: Fix\nRecord:\n", "**New idea slots:** 2\n")
        self.assertIn("0 new ideas", str(e.exception))
        check_new_ideas("New ideas:\n- a\n- b\n", "**New idea slots:** 2\n")

    def test_no_overwrite(self):
        self.run_it(WEEKLY.replace("Move: Learn", "Move: Reach"))
        first = self.ctx / "memos/2026-01-05-weekly.md"
        first.write_text("kept")
        self.assertEqual(self.run_it(WEEKLY.replace("Move: Learn", "Move: Reach")).returncode, 0)
        self.assertEqual(first.read_text(), "kept")
        self.assertTrue((self.ctx / "memos/2026-01-05-weekly-2.md").exists())
        self.assertEqual((self.ctx / "gaps.md").read_text().count("Sign-ups"), 2)

    def test_unwritable_path(self):
        blocker = self.dir / "file"
        blocker.write_text("x")
        r = self.run_it(WEEKLY, path=blocker / "ctx")
        self.assertEqual(r.returncode, 2)
        self.assertTrue(r.stdout.startswith("unknown:"))

    def test_bad_inputs_file_nothing(self):
        for text, store in (("Sure, here it is\n", "local"), (WEEKLY, "dropbox")):
            r = self.run_it(text, store)
            self.assertEqual(r.returncode, 2)
            self.assertFalse(self.ctx.exists())


class NewIdeaAndLearn(unittest.TestCase):
    def test_learn_needs_no_reversible_bet(self):
        from file_memo import check_move
        memo = WEEKLY.replace("Why: no reversible bet\n", "")
        with self.assertRaisesRegex(ValueError, "reversible bet"):
            check_move(memo, "")

    def test_reserved_slot(self):
        from file_memo import check_new_idea_bet
        p = "**New idea slots:** 1\n"
        with self.assertRaises(ValueError):
            check_new_idea_bet("Bets:\n- proposed: a tweak\n", p, "")
        check_new_idea_bet("Bets:\n- proposed new idea: a page\n", p, "")
        check_new_idea_bet("Bets:\n- proposed: a tweak\n", p, "- proposed new idea: earlier\n")
        check_new_idea_bet("", "**New idea slots:** 0\n", "")

    def test_missing_new_idea_bet_files_with_a_gap(self):
        t = FileMemo("test_local"); t.setUp()
        memo = WEEKLY.replace("new idea", "idea")
        self.assertEqual(t.run_it(memo).returncode, 0)
        self.assertIn("reserved slot stays open", (t.ctx / "gaps.md").read_text())


if __name__ == "__main__":
    unittest.main()
