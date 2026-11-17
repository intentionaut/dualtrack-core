"""doctor.py: health lines with fixes, friction counts from events, and "unknown" never 0."""
import contextlib
import datetime
import io
import json
import os
import pathlib
import sys
import unittest

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
import doctor
try:
    import scratch
except ImportError:  # run as tests.test_x from the repo root
    from tests import scratch

NOW = datetime.datetime.now(datetime.timezone.utc)


def run(*args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = doctor.main(list(args))
    return code, buf.getvalue()


class Doctor(unittest.TestCase):
    def setUp(self):
        self.tmp = scratch.mkdtemp()
        self.ctx = os.path.join(self.tmp, "ctx")
        self.profile = os.path.join(self.tmp, "profile.md")
        with open(self.profile, "w") as f:
            f.write(f"**Product:** Fixture\n**Context path:** {self.ctx}\n**Test commands:** true\n")
        os.environ["DUALTRACK_OWNER_DIR"] = self.tmp
        self.addCleanup(os.environ.pop, "DUALTRACK_OWNER_DIR", None)

    def event(self, name, outcome, question=None, days_ago=0, omit_question=False):
        d = os.path.join(self.ctx, "events")
        os.makedirs(d, exist_ok=True)
        ev = {"time": (NOW - datetime.timedelta(days=days_ago)).isoformat(timespec="seconds"),
              "outcome": outcome, "kind": outcome.split(":", 1)[0].strip(), "question": question}
        if omit_question:
            del ev["question"]
        with open(os.path.join(d, name + ".json"), "w") as f:
            json.dump(ev, f)

    def test_no_events_is_unknown_not_zero(self):
        _, out = run(self.profile)
        self.assertIn("unknown", out)
        self.assertNotIn("held changes: 0", out)

    def test_empty_window_is_unknown_not_zero(self):
        self.event("old", "opened: x", days_ago=30)
        _, out = run(self.profile)
        self.assertIn("held changes: unknown (no run events since", out)

    def test_counts_and_unrecorded_fields(self):
        self.event("a", "held: the record holds a token")
        self.event("b", "held for the owner: the engineer needs a key", question="Who buys?")
        self.event("c", "stopped: no sandbox is available for branch code here")
        self.event("d", "stopped: over the $5 cap reading the brief doc, 5.2")
        self.event("e", "opened: Fix it, https://github.invalid/o/r/pull/1")
        self.event("f", "held: too old", days_ago=30)
        _, out = run(self.profile)
        for want in ("runs: 5", "held changes: 2", "owner questions: 1", "sandbox stops: 1", "run-cap overruns: 1",
                     "preflight stops: unknown", "tamper stops: unknown"):
            self.assertIn(want, out)

    def test_field_missing_from_events_is_unknown(self):
        self.event("a", "opened: x", omit_question=True)
        _, out = run(self.profile)
        self.assertIn("owner questions: unknown", out)

    def test_since_flag(self):
        self.event("old", "held: old", days_ago=30)
        since = (NOW - datetime.timedelta(days=60)).date().isoformat()
        _, out = run(self.profile, "--since", since)
        self.assertIn("held changes: 1", out)
        self.assertEqual(run(self.profile, "--since", "nope")[0], 2)

    def test_tamper_problem_shows_its_fix(self):
        orig = doctor.tamper.changed
        doctor.tamper.changed = lambda kit: ["scripts/guards.sh"]
        self.addCleanup(setattr, doctor.tamper, "changed", orig)
        _, out = run(self.profile)
        self.assertIn("PROBLEM  tamper check: safety stop: scripts/guards.sh changed", out)
        self.assertIn("fix: put the file back with `git checkout -- <file>`", out)

    def test_clean_kit_tamper_ok(self):
        orig = doctor.tamper.changed
        doctor.tamper.changed = lambda kit: []
        self.addCleanup(setattr, doctor.tamper, "changed", orig)
        self.assertEqual(doctor.health("")[0][:2], ("tamper check", None))

    def test_report_is_a_fenced_block(self):
        self.event("a", "held: x")
        _, out = run(self.profile, "--report")
        self.assertTrue(out.startswith("```\nDualtrack doctor\n"))
        self.assertTrue(out.rstrip().endswith("```"))
        self.assertIn("held changes: 1", out)
        self.assertNotIn("```", run(self.profile)[1])

    def test_unreachable_state_repo_has_fix(self):
        import subprocess
        state = os.path.join(self.tmp, "state")
        subprocess.run(["git", "init", "-q", state], check=True)
        subprocess.run(["git", "-C", state, "remote", "add", "origin", os.path.join(self.tmp, "nowhere.git")], check=True)
        problem, fix = doctor.state_repo(state)
        self.assertIn("could not be read", problem)
        self.assertIn("ls-remote", fix)

    def test_missing_profile_prints_usage(self):
        self.assertEqual(run("/no/such/profile.md")[0], 2)


if __name__ == "__main__":
    unittest.main()
