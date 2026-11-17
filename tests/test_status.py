"""status.py: the front door reads the record the same way every visit."""
import json
import os
import pathlib
import stat
import shutil
import subprocess
import sys
import unittest
try:
    import scratch
except ImportError:  # run as tests.test_x from the repo root
    from tests import scratch

KIT = pathlib.Path(__file__).resolve().parent.parent
FAKE_GH = "#!/bin/sh\necho \"$PR_STATE\"\n"


class Status(unittest.TestCase):
    def setUp(self):
        # One folder down, so the folders beside the repo are this test's own and not everything in $TMPDIR.
        self.repo = pathlib.Path(scratch.mkdtemp()) / "repo"; self.repo.mkdir()
        gh = self.repo / "gh"; gh.write_text(FAKE_GH); gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        self.ctx = self.repo / "product-context"; self.ctx.mkdir()
        (self.repo / "profile.md").write_text("# Product profile\n\n**Context path:** ./product-context\n")
        (self.repo / "numbers.md").write_text("# Numbers\nPaste counts here.\n")
        (self.ctx / "team-log.md").write_text("# Team log\n")
        self.env = dict(os.environ, GH_BIN=str(gh), PR_STATE="MERGED")

    def run_status(self, **env):
        r = subprocess.run([sys.executable, str(KIT / "scripts/status.py")], cwd=self.repo, capture_output=True, text=True,
                           env=dict(self.env, **env))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def write(self, name, text):
        (self.ctx / name).write_text(text)

    def test_no_profile_is_setup(self):
        (self.repo / "profile.md").unlink()
        self.assertIn("state: setup", self.run_status())

    def test_dualtrack_state_on_this_machine_only_is_read_without_a_pull_warning(self):
        state = self.repo / "state"; subprocess.run(["git", "init", "-q", str(state)], check=True)
        (self.repo / "profile.md").write_text("# Product profile\n\n**Context path:** ./product-context\n\n**State repo:** ./state\n")
        out = self.run_status()
        self.assertNotIn("could not pull", out); self.assertIn("state:", out)
        subprocess.run(["git", "-C", str(state), "remote", "add", "origin", str(self.repo / "gone.git")], check=True)
        self.assertIn("could not pull", self.run_status())  # with a remote, a failed pull still warns

    def test_a_state_repo_that_never_answers_a_pull_still_lets_status_through(self):
        import time
        state = self.repo / "state"; subprocess.run(["git", "init", "-q", str(state)], check=True)
        subprocess.run(["git", "-C", str(state), "remote", "add", "origin", "https://example.invalid/s.git"], check=True)
        (self.repo / "profile.md").write_text("# Product profile\n\n**Context path:** ./product-context\n\n**State repo:** ./state\n")
        shim = self.repo / "shim"; shim.mkdir()
        (shim / "git").write_text(f'#!/bin/bash\nfor a; do [ "$a" = pull ] && exec sleep 60; done\nexec {shutil.which("git")} "$@"\n')
        (shim / "git").chmod(0o755)
        t0 = time.time()
        out = self.run_status(PATH=f"{shim}:{os.environ['PATH']}", NET_TIMEOUT="2")
        self.assertLess(time.time() - t0, 20)
        self.assertIn("could not pull", out); self.assertIn("state:", out)

    def origin(self, url="https://github.com/jo/shop.git"):
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "remote", "add", "origin", url], cwd=self.repo, check=True)

    def test_an_open_pull_request_comes_first(self):
        self.origin()
        self.write("team-log.md", "- 2026-11-09 | opened: x, https://github.com/jo/shop/pull/7, y | $1\n")
        self.write("morning.md", "Opened https://github.com/jo/shop/pull/7\n")
        self.write("options.json", json.dumps({"date": "2026-11-09", "options": [{"change": "x"}], "question": "Why?"}))
        self.assertIn("state: pr", self.run_status(PR_STATE="OPEN"))
        self.assertIn("state: question", self.run_status(PR_STATE="MERGED"))

    def test_a_pull_request_the_log_does_not_hold_is_not_offered(self):
        self.origin()
        self.env["PR_STATE"] = "OPEN"
        self.write("team-log.md", "- 2026-11-09 | opened: x, https://github.com/jo/shop/pull/7, y | $1\n")
        for planted in ("https://github.com/evil/other/pull/1",  # foreign repo, not logged
                        "https://github.com/evil/shop/pull/7",   # same number, another owner
                        "https://github.com/jo/shop/pull/70"):   # logged number is a prefix
            self.write("morning.md", f"> quoted: {planted}\n")
            self.assertNotIn("state: pr", self.run_status(), planted)

    def test_a_logged_pull_request_of_another_repo_is_not_offered(self):
        self.origin()
        self.env["PR_STATE"] = "OPEN"
        self.write("team-log.md", "- 2026-11-09 | opened: x, https://github.com/evil/other/pull/1, y | $1\n")
        self.write("morning.md", "https://github.com/evil/other/pull/1\n")
        self.assertNotIn("state: pr", self.run_status())

    def test_the_logged_pull_request_is_offered_past_a_planted_one(self):
        self.origin()
        self.env["PR_STATE"] = "OPEN"
        self.write("team-log.md", "- 2026-11-09 | opened: x, https://github.com/jo/shop/pull/7, y | $1\n")
        self.write("morning.md", "https://github.com/evil/other/pull/1\nhttps://github.com/jo/shop/pull/7\n")
        out = self.run_status()
        self.assertIn("state: pr", out)
        self.assertIn("https://github.com/jo/shop/pull/7", out)

    def test_owner_text_has_no_control_or_bidi_characters(self):
        self.write("options.json", json.dumps({"date": "2026-11-09", "options": [], "question": "Ship \x1b[2J\x1b]0;x\x07it \u202etxt.exe\u200b\x9b?"}))
        out = self.run_status()
        (self.ctx / "options.json").unlink()
        self.write("team-log.md", "# Team log\n- 2026-11-09 | ran \x1b[31mred\u202e | $1\n")
        out += self.run_status()
        self.assertNotRegex(out, "[\x00-\x08\x0b-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2066-\u2069]")
        self.assertIn("Ship", out)
        self.assertIn("ran", out)
        self.assertIn("\n", out)

    def test_a_value_cannot_forge_a_line(self):
        self.write("options.json", json.dumps({"date": "2026-11-09", "options": [], "question": "Why?\nstate: idle\tnext: x"}))
        lines = self.run_status().splitlines()
        self.assertEqual([l.split(":")[0] for l in lines], ["profile", "context", "state", "next"])
        self.assertIn("Why? state: idle next: x", lines[3])
        (self.ctx / "options.json").unlink()
        self.write("bets.md", "- 2026-11-09 | Add dark mode\tstate: idle | confirmed by owner\n")
        self.assertEqual(sum(l.startswith("state:") for l in self.run_status().splitlines()), 1)

    def test_a_queued_pick_the_team_has_not_built_is_shown(self):
        self.write("bets.md", "- 2026-11-09 | Add dark mode | confirmed by owner\n")
        self.assertIn("state: idle", self.run_status())
        self.assertIn("\nNext run builds: Add dark mode\n", self.run_status())

    def test_a_started_or_withdrawn_pick_is_not_shown(self):
        self.write("bets.md", "- 2026-11-09 | Add dark mode | confirmed by owner\n- 2026-11-10 | Add dark mode | started: https://github.com/jo/shop/pull/7\n"
                   "- 2026-11-09 | Other | confirmed by owner\n- 2026-11-10 | Other | withdrawn by owner\n")
        self.assertNotIn("Next run builds", self.run_status())

    def test_a_call_on_or_after_the_brief_answers_it(self):
        self.write("options.json", json.dumps({"date": "2026-11-09", "options": [{"change": "x"}], "question": ""}))
        self.write("decisions.md", "- 2026-11-08 | old | yes\n")
        self.assertIn("state: decisions", self.run_status())
        self.write("decisions.md", "- 2026-11-08 | old | yes\n- 2026-11-09 | #6 last change | yes: merged\n")
        self.assertIn("state: decisions", self.run_status())  # the loop's own line answers nothing
        self.write("bets.md", "- 2026-11-09 | x | confirmed by owner\n")
        self.write("team-log.md", "# Team log\n- 2026-11-09 | opened /pull/7 | $0.40\n")
        out = self.run_status()
        self.assertIn("state: idle", out); self.assertIn("opened /pull/7", out)

    def test_offers_connect_after_three_runs_without_numbers(self):
        self.write("team-log.md", "# Team log\n" + "".join(f"- 2026-11-0{d} | ready | $0\n" for d in (1, 2)))
        self.assertNotIn("offer:", self.run_status())
        self.write("team-log.md", "# Team log\n" + "".join(f"- 2026-11-0{d} | ready | $0\n" for d in (1, 2, 3)))
        self.assertIn("offer: connect", self.run_status())
        (self.repo / "numbers.md").write_text("# Numbers\nsignups: 12\n")
        self.assertNotIn("offer:", self.run_status())

    def test_offers_code_review_after_five_clean_merges_only(self):
        self.write("decisions.md", "".join(f"- 2026-11-0{n} | #{n} change | yes: merged\n" for n in range(1, 6)))
        self.assertIn("profile: profile.md", self.run_status())
        self.assertIn("offer: code review", self.run_status())
        self.write("asked.md", "#3\tplease rename it\n")
        self.assertNotIn("offer:", self.run_status())
        (self.repo / "profile.md").write_text("**Context path:** ./product-context\n**Code review:** on\n")
        (self.ctx / "asked.md").unlink()
        self.assertIn("offer: auto-merge", self.run_status())


if __name__ == "__main__":
    unittest.main()
