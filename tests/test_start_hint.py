"""The session-start hint: shown when the repo has no profile, silent when it has one."""
import json
import pathlib
import subprocess
import sys
import unittest

KIT = pathlib.Path(__file__).resolve().parent.parent
try:
    import scratch
except ImportError:  # run as tests.test_x from the repo root
    from tests import scratch

HINT = "Dualtrack is installed. Type /dualtrack:dualtrack to start.\n"


def run_in(folder):
    return subprocess.run([sys.executable, str(KIT / "scripts" / "start_hint.py")], cwd=folder,
                          capture_output=True, text=True)


class StartHint(unittest.TestCase):
    def test_no_profile_prints_the_hint(self):
        r = run_in(scratch.mkdtemp())
        self.assertEqual((r.returncode, r.stdout), (0, HINT))

    def test_a_profile_prints_nothing(self):
        d = pathlib.Path(scratch.mkdtemp())
        (d / "profile.md").write_text("# Profile\n")
        r = run_in(d)
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_the_hook_runs_it_at_session_start(self):
        cmds = [h["command"] for e in json.loads((KIT / "hooks" / "hooks.json").read_text())["hooks"]["SessionStart"] for h in e["hooks"]]
        self.assertTrue(any("scripts/start_hint.py" in c for c in cmds))

    def test_readme_says_how_to_start_once_installed(self):
        self.assertIn("Once installed, type `/dualtrack:dualtrack` to start.", (KIT / "README.md").read_text())


if __name__ == "__main__":
    unittest.main()
