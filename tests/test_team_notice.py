"""#241: a soft note points to Team once a state repo holds the 6 product teams Free covers. It never blocks, and it can be hidden."""
import io
import os
import pathlib
import sys
import unittest
from contextlib import redirect_stdout

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
import decide
import setup_apply

try:
    import scratch
except ImportError:
    from tests import scratch


class Fixture(unittest.TestCase):
    """A product repo (cwd) whose profile names a state repo holding `n` product folders."""

    def setUp(self):
        self.root = pathlib.Path(scratch.mkdtemp())
        self.cwd = os.getcwd()
        self.ctx = self.root / "ctx"
        self.ctx.mkdir()
        (self.root / "product").mkdir()
        os.chdir(self.root / "product")

    def tearDown(self):
        os.chdir(self.cwd)

    def teams(self, n):
        state = self.root / f"state{n}"
        for i in range(n):
            (state / f"p{i}").mkdir(parents=True)
            (state / f"p{i}" / "profile.md").write_text("x\n")
        (state / "not-a-team").mkdir()  # no profile.md: not a team
        pathlib.Path("profile.md").write_text(f"**Context path:** {self.ctx}\n**State repo:** {state}\n")
        return state


class TeamNotice(Fixture):
    def test_no_note_at_five(self):
        self.teams(5)
        self.assertEqual(decide.team_notice(str(self.ctx)), "")

    def test_note_at_six_and_seven(self):
        for n in (6, 7):
            self.teams(n)
            note = decide.team_notice(str(self.ctx))
            self.assertIn(f"holds {n} product teams", note)
            self.assertIn("Team tier: https://dualtrack.intentionaut.com/pricing/.", note)
            self.assertIn("decide.py notice off", note)

    def test_enterprise_note_at_twelve_and_thirteen(self):
        for n in (11, 12, 13):
            self.teams(n)
            note = decide.team_notice(str(self.ctx))
            self.assertIn(f"holds {n} product teams", note)
            self.assertEqual("needs Enterprise: talk to us at https://dualtrack.intentionaut.com/contact/. To hide this: decide.py notice off" in note, n >= 12, note)
            self.assertEqual("needs the Team tier" in note, n < 12, note)

    def test_no_state_repo_no_note(self):
        pathlib.Path("profile.md").write_text(f"**Context path:** {self.ctx}\n")
        self.assertEqual(decide.team_notice(str(self.ctx)), "")

    def test_same_count_as_the_free_limit(self):
        state = self.teams(6)
        self.assertEqual(decide.teams_filed(state), 6)
        self.assertEqual(setup_apply.FREE_TEAMS, decide.FREE_TEAMS)
        with self.assertRaises(SystemExit):  # a 7th new product stops where the notice began
            setup_apply.team_limit(state, state / "new" / "profile.md")


class DecideCommand(Fixture):
    def run_decide(self, *argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = decide.main(list(argv), today="2026-11-14", save=False)
        return code, buf.getvalue()

    def test_try_still_records_and_shows_note_at_six(self):
        self.teams(6)
        code, out = self.run_decide("try", "Add a demo page")
        self.assertEqual(code, 0)
        self.assertIn("confirmed: Add a demo page", out)
        self.assertIn("holds 6 product teams", out)

    def test_nothing_blocked_or_said_at_five(self):
        self.teams(5)
        code, out = self.run_decide("try", "Add a demo page")
        self.assertEqual(code, 0)
        self.assertIn("confirmed: Add a demo page", out)
        self.assertNotIn("product teams", out)

    def test_notice_off_hides_it(self):
        for n in (7, 13):
            self.teams(n)
            self.assertIn("product teams", self.run_decide("try", "A bet")[1])
            self.assertEqual(self.run_decide("notice", "off")[0], 0)
            code, out = self.run_decide("try", "Another bet")
            self.assertEqual(code, 0)
            self.assertNotIn("product teams", out)
            os.remove(self.ctx / "team-notice-off")


if __name__ == "__main__":
    unittest.main()
