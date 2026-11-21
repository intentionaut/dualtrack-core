"""The locked-area guard: a PreToolUse hook that denies the edit itself, before it happens (INT-241).

Each test runs the real hook script with the JSON Claude Code sends it, so removing the hook makes them fail.
"""
import json
import os
import pathlib
import subprocess
import sys
import unittest

KIT = pathlib.Path(__file__).resolve().parent.parent
HOOK = KIT / "scripts/lock_hook.py"
sys.path.insert(0, str(KIT / "scripts"))
import safety_card as sc  # noqa: E402
try:
    import scratch
except ImportError:  # run as tests.test_x from the repo root
    from tests import scratch

LOGIN = ("Login and accounts", sc.AREAS["Login and accounts"])
PAYMENTS = ("Payments and checkout", sc.AREAS["Payments and checkout"])


class Hook(unittest.TestCase):
    def setUp(self):
        self.t = pathlib.Path(scratch.mkdtemp())
        self.profile = self.t / "profile.md"
        self.allowed = self.t / "allowed.md"
        self.profile.write_text(sc.save("**Mode:** acquisition\n", [LOGIN]))

    def call(self, tool, tool_input, profile="default", env=None):
        e = {k: v for k, v in os.environ.items() if not k.startswith("DUALTRACK_LOCK")}
        if profile == "default":
            e["DUALTRACK_LOCK_PROFILE"] = str(self.profile)
        elif profile:
            e["DUALTRACK_LOCK_PROFILE"] = profile
        e.update(DUALTRACK_LOCK_ALLOWED=str(self.allowed), DUALTRACK_LOCK_BET="Shorter sign-up form", **(env or {}))
        r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps({"tool_name": tool, "tool_input": tool_input, "cwd": str(self.t)}),
                           capture_output=True, text=True, env=e)
        return r.returncode, r.stderr

    def denied(self, tool, tool_input, **kw):
        code, err = self.call(tool, tool_input, **kw)
        self.assertEqual(code, 2, err)
        return err

    def allowed_through(self, tool, tool_input, **kw):
        code, err = self.call(tool, tool_input, **kw)
        self.assertEqual(code, 0, err)

    def test_an_edit_to_a_locked_file_is_denied_with_the_plain_stop_line(self):
        for tool, key in (("Edit", "file_path"), ("Write", "file_path"), ("MultiEdit", "file_path"), ("NotebookEdit", "notebook_path")):
            err = self.denied(tool, {key: str(self.t / "src/auth/login.py")})
            self.assertIn("this change needs login and accounts", err)
            self.assertIn("1) Allow a change", err)
            self.assertIn("BLOCKED: locked area Login and accounts", err)
        self.denied("Edit", {"file_path": "src/auth/login.py"})  # a relative path counts too

    def test_an_unlocked_edit_and_a_test_edit_pass(self):
        self.allowed_through("Edit", {"file_path": str(self.t / "src/pages/about.astro")})
        self.allowed_through("Write", {"file_path": str(self.t / "tests/test_login.py")})
        self.allowed_through("Read", {"file_path": str(self.t / "src/auth/login.py")})

    def test_an_area_the_owner_allowed_for_this_bet_passes(self):
        self.allowed.write_text("- 2026-11-20 | Shorter sign-up form | Login and accounts\n")
        self.allowed_through("Edit", {"file_path": str(self.t / "src/auth/login.py")})
        self.allowed.write_text("- 2026-11-20 | Some other bet | Login and accounts\n")
        self.denied("Edit", {"file_path": str(self.t / "src/auth/login.py")})

    def test_an_allow_opens_only_the_area_it_names(self):
        # "Allow a change to login, just for this bet" must not open payments too.
        self.profile.write_text(sc.save("**Mode:** acquisition\n", [LOGIN, PAYMENTS]))
        self.allowed.write_text("- 2026-11-20 | Shorter sign-up form | Login and accounts\n")
        self.allowed_through("Edit", {"file_path": str(self.t / "src/auth/login.py")})
        err = self.denied("Edit", {"file_path": str(self.t / "src/checkout/pay.py")})
        self.assertIn("payments and checkout", err)
        self.denied("Bash", {"command": "rm src/auth/login.py src/checkout/pay.py"})

    def test_an_allow_for_another_kind_of_hold_opens_no_locked_area(self):
        self.allowed.write_text("- 2026-11-20 | Shorter sign-up form | allowed by owner\n")
        self.denied("Edit", {"file_path": str(self.t / "src/auth/login.py")})

    def test_a_profile_with_no_locked_areas_changes_nothing(self):
        self.profile.write_text("**Mode:** acquisition\n")
        self.allowed_through("Edit", {"file_path": str(self.t / "src/auth/login.py")})
        self.allowed_through("Bash", {"command": "rm src/auth/login.py"})

    def test_outside_a_dualtrack_run_the_hook_does_nothing(self):
        self.allowed_through("Edit", {"file_path": "src/auth/login.py"}, profile="")

    def test_it_fails_closed_when_the_profile_cannot_be_read_or_the_input_is_garbage(self):
        self.denied("Edit", {"file_path": "src/pages/about.astro"}, profile=str(self.t / "missing.md"))
        e = dict(os.environ, DUALTRACK_LOCK_PROFILE=str(self.profile))
        r = subprocess.run([sys.executable, str(HOOK)], input="not json", capture_output=True, text=True, env=e)
        self.assertEqual(r.returncode, 2)

    def test_a_bash_command_that_writes_a_locked_path_is_denied(self):
        for cmd in ("echo x > src/auth/login.py", "echo x >> src/auth/login.py", "echo x >src/auth/login.py", "sed -i 's/a/b/' src/auth/login.py",
                    "sed -i.bak s/a/b/ src/auth/login.py", "echo x | tee src/auth/login.py", "mv /tmp/x src/auth/login.py", "cp /tmp/x src/auth/login.py",
                    "rm src/auth/login.py", "git checkout main -- src/auth/login.py", "git restore src/auth/login.py", "git add -A && rm src/auth/login.py"):
            err = self.denied("Bash", {"command": cmd})
            self.assertIn("login and accounts", err, cmd)

    def test_git_apply_is_read_for_the_files_the_patch_names(self):
        (self.t / "p.diff").write_text("--- a/src/auth/login.py\n+++ b/src/auth/login.py\n@@ -1 +1 @@\n-a\n+b\n")
        self.denied("Bash", {"command": "git apply p.diff"})
        (self.t / "q.diff").write_text("--- a/src/pages/a.py\n+++ b/src/pages/a.py\n@@ -1 +1 @@\n-a\n+b\n")
        self.allowed_through("Bash", {"command": "git apply q.diff"})

    def test_a_bash_read_or_an_unrelated_write_is_allowed(self):
        for cmd in ("cat src/auth/login.py", "grep -n x src/auth/login.py", "git status", "git add src/auth/login.py", "echo x > src/pages/about.astro",
                    "python3 -m unittest tests.test_login", "git diff -- src/auth/login.py", "cp src/auth/login.py /tmp/copy.py"):
            self.allowed_through("Bash", {"command": cmd})


class Backstop(unittest.TestCase):
    def test_a_missed_write_to_a_locked_file_is_put_back_from_the_base(self):
        t = pathlib.Path(scratch.mkdtemp())

        def git(*a):
            return subprocess.run(["git", "-C", str(t), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True, text=True).stdout.strip()
        git("init", "-q", "-b", "main")
        (t / "src/auth").mkdir(parents=True)
        (t / "src/auth/login.py").write_text("safe = 1\n")
        (t / "src/about.py").write_text("a = 1\n")
        git("add", "-A")
        git("commit", "-qm", "base")
        base = git("rev-parse", "HEAD")
        git("checkout", "-q", "-b", "work")
        (t / "src/auth/login.py").write_text("safe = 0\n")
        (t / "src/auth/password.py").write_text("new = 1\n")  # a new locked file: removed, not restored
        (t / "src/about.py").write_text("a = 2\n")
        git("add", "-A")
        git("commit", "-qm", "work")
        (t / "profile.md").write_text(sc.save("", [LOGIN]))
        (t / "diff.txt").write_text("M\tsrc/auth/login.py\nA\tsrc/auth/password.py\nM\tsrc/about.py\n")
        r = subprocess.run([sys.executable, str(KIT / "scripts/safety_card.py"), "revert", str(t / "profile.md"), str(t / "diff.txt"), base],
                           cwd=t, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((t / "src/auth/login.py").read_text(), "safe = 1\n")
        self.assertFalse((t / "src/auth/password.py").exists())
        self.assertEqual((t / "src/about.py").read_text(), "a = 2\n")  # the rest of the work stays
        self.assertEqual(git("diff", "--name-only", base, "HEAD"), "src/about.py")

    def test_the_backstop_keeps_an_allowed_area_and_puts_back_the_rest(self):
        t = pathlib.Path(scratch.mkdtemp())

        def git(*a):
            return subprocess.run(["git", "-C", str(t), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True, text=True).stdout.strip()
        git("init", "-q", "-b", "main")
        (t / "src/auth").mkdir(parents=True)
        (t / "src/checkout").mkdir(parents=True)
        (t / "src/auth/login.py").write_text("safe = 1\n")
        (t / "src/checkout/pay.py").write_text("p = 1\n")
        git("add", "-A")
        git("commit", "-qm", "base")
        base = git("rev-parse", "HEAD")
        (t / "src/auth/login.py").write_text("safe = 0\n")
        (t / "src/checkout/pay.py").write_text("p = 2\n")
        git("commit", "-qam", "work")
        (t / "profile.md").write_text(sc.save("", [LOGIN, PAYMENTS]))
        (t / "diff.txt").write_text("M\tsrc/auth/login.py\nM\tsrc/checkout/pay.py\n")
        (t / "allowed.md").write_text("- 2026-11-20 | Shorter sign-up form | Login and accounts\n")
        env = {**os.environ, "DUALTRACK_LOCK_ALLOWED": str(t / "allowed.md"), "DUALTRACK_LOCK_BET": "Shorter sign-up form"}
        r = subprocess.run([sys.executable, str(KIT / "scripts/safety_card.py"), "revert", str(t / "profile.md"), str(t / "diff.txt"), base],
                           cwd=t, capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((t / "src/auth/login.py").read_text(), "safe = 0\n")  # allowed: kept
        self.assertEqual((t / "src/checkout/pay.py").read_text(), "p = 1\n")  # not allowed: put back
        r = subprocess.run([sys.executable, str(KIT / "scripts/safety_card.py"), "locked", str(t / "profile.md"), str(t / "diff.txt"), "Shorter sign-up form", "oneline"],
                           cwd=t, capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 4)
        self.assertIn("payments and checkout", r.stdout)
        self.assertNotIn("login", r.stdout)


class Wiring(unittest.TestCase):
    def test_the_plugin_hooks_file_registers_the_guard(self):
        pre = json.loads((KIT / "hooks/hooks.json").read_text())["hooks"]["PreToolUse"]
        cmds = [h["command"] for g in pre for h in g["hooks"]]
        self.assertTrue(any("lock_hook.py" in c for c in cmds))
        self.assertIn("Bash", pre[0]["matcher"])
        self.assertIn("NotebookEdit", pre[0]["matcher"])

    def test_the_loop_gives_every_agent_session_the_guard_through_its_own_settings(self):
        loop = (KIT / "scripts/daily_loop.sh").read_text()
        # The agents load no settings from disk (--setting-sources=), so the guard rides in --settings or it is not there.
        self.assertIn("lock_hook.py", loop)
        self.assertIn('"PreToolUse"', loop)
        for name in ("DUALTRACK_LOCK_PROFILE", "DUALTRACK_LOCK_ALLOWED", "DUALTRACK_LOCK_BET"):
            self.assertIn(name, loop)
        # limit.py runs everything after it as the command, so the variables must come before it.
        line = next(l for l in loop.splitlines() if "DUALTRACK_LOCK_PROFILE=" in l)
        self.assertLess(line.index("DUALTRACK_LOCK_PROFILE="), line.index("AGENT_LIMIT"))


if __name__ == "__main__":
    unittest.main()
