"""setup_check.py and setup_apply.py: the same checks and the same filing, every setup."""
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import unittest
from unittest import mock
try:
    import scratch
except ImportError:  # run as tests.test_x from the repo root
    from tests import scratch

KIT = pathlib.Path(__file__).resolve().parent.parent
FAKE_GH = r'''#!/usr/bin/env python3
import os, subprocess, sys
a = sys.argv[1:]
open(os.environ["GH_LOG"], "a").write(" ".join(a) + "\n")
if a[:2] == ["auth", "status"]: sys.exit(0)
if a[:2] == ["repo", "view"] and "url" in a and os.environ.get("STATE_ORIGIN"): print(os.environ["STATE_ORIGIN"]); sys.exit(0)
if a[:2] == ["repo", "view"] and a[2].endswith("/" + os.environ.get("STATE_NAME", "dualtrack-state")): sys.exit(0 if os.environ.get("STATE_EXISTS") else 1)
if a[:2] == ["repo", "view"]: print("PRIVATE"); sys.exit(0)
if a[:2] == ["repo", "clone"]: sys.exit(subprocess.run(["git", "clone", "-q", os.environ["STATE_ORIGIN"], a[3]]).returncode)
if a[:2] == ["repo", "create"]: sys.exit(0)
if a[0] == "api" and a[1].endswith("/contents"): print(os.environ.get("STATE_DIRS", "")); sys.exit(0)
if a[0] == "api": sys.exit(0 if os.environ.get("STATE_HAS") and os.environ["STATE_HAS"] in a[1] else 1)
sys.exit(1)
'''
SETUP_MD = "# Product profile\n\n**Mode:** acquisition\n\n**Test commands:** `python3 -m unittest discover -s tests -t .`\n\nStarting options:\n- x\n"
PASSING = "import unittest\n\nclass T(unittest.TestCase):\n    def test_ok(self):\n        self.assertTrue(True)\n"


class Setup(unittest.TestCase):
    def setUp(self):
        self.t = pathlib.Path(scratch.mkdtemp())
        gh = self.t / "gh"; gh.write_text(FAKE_GH); gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        self.repo = self.t / "shop"; self.repo.mkdir()
        self.git("init", "-q", "-b", "main"); self.git("remote", "add", "origin", "https://github.com/jo/shop.git")
        (self.repo / "tests").mkdir(); (self.repo / "tests/__init__.py").write_text(""); (self.repo / "tests/test_a.py").write_text(PASSING)
        (self.repo / "README.md").write_text("x\n")
        self.git("add", "."); self.git("-c", "user.name=t", "-c", "user.email=t@t.invalid", "commit", "-qm", "init")
        self.env = dict(os.environ, GH_BIN=str(gh), GH_LOG=str(self.t / "gh.log"))
        self.env.pop("ANTHROPIC_API_KEY", None)

    def git(self, *a, cwd=None):
        return subprocess.run(["git", "-C", str(cwd or self.repo), *a], capture_output=True, text=True, check=True).stdout

    def check(self, *args, **env):
        r = subprocess.run([sys.executable, str(KIT / "scripts/setup_check.py"), *args], cwd=self.repo, capture_output=True,
                           text=True, env=dict(self.env, **env))
        return r.returncode, r.stdout, json.loads(r.stdout.strip().splitlines()[-1])

    def apply(self, *args, **env):
        return subprocess.run([sys.executable, str(KIT / "scripts/setup_apply.py"), *args], cwd=self.repo, capture_output=True,
                              text=True, env=dict(self.env, **env))

    def test_a_ready_repo_passes_with_its_facts(self):
        code, out, facts = self.check(STATE_EXISTS="1")
        self.assertEqual(code, 0, out)
        self.assertIn("Tests pass: yes", out); self.assertIn("1 tests", out)
        self.assertEqual((facts["owner"], facts["visibility"], facts["state_repo_exists"], facts["web"]), ("jo", "PRIVATE", True, False))

    def local_setup(self):
        """Set up with no GitHub, then add a GitHub remote to the product: the later move."""
        self.git("remote", "remove", "origin")
        (self.repo / "setup.md").write_text(SETUP_MD)
        r = self.apply(*self.answers("state", "local"), **self.git_id())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.git("remote", "add", "origin", "https://github.com/jo/shop.git")
        return self.t / "dualtrack-state"

    def git_id(self):
        return dict(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t.invalid", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t.invalid")

    def test_after_adding_github_setup_finds_the_local_record_and_does_not_start_again(self):
        self.local_setup()
        code, out, facts = self.check()
        self.assertEqual(code, 0, out); self.assertTrue(facts["set_up"]); self.assertTrue(facts["local_state"])
        self.assertIn("--join", out); self.assertNotIn("Tests pass", out)

    def test_join_puts_the_local_record_on_github_with_its_history_only_when_agreed(self):
        state = self.local_setup()
        log = self.git("log", "--format=%H", cwd=state)
        r = self.apply("--join")
        self.assertNotEqual(r.returncode, 0); self.assertIn("--create-state", r.stderr)
        self.assertNotIn("repo create", (self.t / "gh.log").read_text() if (self.t / "gh.log").exists() else "")
        bare = self.t / "state.git"; subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        r = self.apply("--join", "--create-state", STATE_ORIGIN=str(bare))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("repo create jo/dualtrack-state --private", (self.t / "gh.log").read_text())
        self.assertEqual(subprocess.run(["git", "--git-dir", str(bare), "log", "--all", "--format=%H"], capture_output=True, text=True).stdout, log)
        self.assertEqual(r.stdout.strip().splitlines()[-1], "../dualtrack-state/shop/profile.md")

    def test_join_never_shares_another_products_record_without_say_so(self):
        state = self.local_setup()
        (state / "beta").mkdir(); (state / "beta/profile.md").write_text("# beta\n")
        bare = self.t / "state.git"; subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        r = self.apply("--join", "--create-state", STATE_ORIGIN=str(bare))
        self.assertNotEqual(r.returncode, 0); self.assertIn("also holds beta", r.stderr); self.assertIn("--share-all", r.stderr)
        self.assertNotIn("repo create", (self.t / "gh.log").read_text() if (self.t / "gh.log").exists() else "")
        self.assertEqual(self.git("remote", cwd=state), "")
        r = self.apply("--join", "--create-state", "--share-all", STATE_ORIGIN=str(bare))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_join_finds_a_record_filed_under_the_folder_name_when_the_repo_name_differs(self):
        state = self.local_setup()
        self.git("remote", "set-url", "origin", "https://github.com/jo/shop-app.git")
        bare = self.t / "state.git"; subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        r = self.apply("--join", "--create-state", STATE_ORIGIN=str(bare))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip().splitlines()[-1], "../dualtrack-state/shop/profile.md")

    def test_join_stops_when_github_already_has_a_state_repo_of_that_name(self):
        self.local_setup()
        r = self.apply("--join", "--create-state", STATE_EXISTS="1")
        self.assertNotEqual(r.returncode, 0); self.assertIn("already exists", r.stderr)
        self.assertEqual(self.git("remote", cwd=self.t / "dualtrack-state"), "")

    def test_no_sandbox_stops_early_with_the_doctors_fix_line(self):
        bare = self.t / "bin"; bare.mkdir()
        (bare / "git").symlink_to(shutil.which("git"))  # a PATH with neither sandbox-exec nor bwrap
        r = subprocess.run([sys.executable, str(KIT / "scripts/setup_check.py")], cwd=self.repo, capture_output=True, text=True,
                           env={k: v for k, v in dict(self.env, PATH=str(bare)).items() if k != "DUALTRACK_SANDBOXED"})
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn("no sandbox available for branch code", r.stdout)
        self.assertIn("install bubblewrap", r.stdout)  # doctor.py's own fix line
        self.assertIn("sudo tee /etc/sysctl.d/60-dualtrack-bwrap.conf && sudo sysctl --system", r.stdout)  # the form that survives a reboot
        self.assertIn("whole machine", r.stdout); self.assertIn("lost on reboot", r.stdout)
        self.assertNotIn("A GitHub repo", r.stdout)  # stopped before anything else ran

    def test_a_folder_that_is_not_a_git_repo_stops_first(self):
        import shutil; shutil.rmtree(self.repo / ".git")
        code, out, facts = self.check()
        self.assertEqual((code, facts["failed"]), (1, "A git repo")); self.assertIn("Nothing was changed", out)

    def test_no_github_remote_keeps_going_with_dualtrack_state_on_this_machine(self):
        self.git("remote", "remove", "origin")
        code, out, facts = self.check()
        self.assertEqual(code, 0, out)
        self.assertEqual((facts["owner"], facts["repo"], facts["local_only"], facts["state_repo"]), (None, "shop", True, "../dualtrack-state"))
        self.assertIn("A GitHub repo: not yet", out); self.assertIn("Tests pass: yes", out)
        self.assertFalse((self.t / "gh.log").exists(), "no GitHub call without a GitHub repo")
        self.assertFalse((self.t / "dualtrack-state").exists(), "the check changes nothing")

    def test_without_github_setup_files_the_record_in_a_local_git_repo_and_keeps_its_history_when_pushed_later(self):
        self.git("remote", "remove", "origin")
        (self.repo / "setup.md").write_text(SETUP_MD)
        git_id = dict(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t.invalid", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t.invalid")
        r = self.apply(*self.answers("state", "local"), **git_id)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        state = self.t / "dualtrack-state"
        self.assertEqual(r.stdout.strip().splitlines()[-1], "../dualtrack-state/shop/profile.md")
        self.assertIn("**State repo:** ../dualtrack-state", (state / "shop/profile.md").read_text())
        self.assertIn("on this machine", r.stdout); self.assertNotIn("NOT pushed", r.stdout)
        self.assertFalse((self.t / "gh.log").exists())
        log = self.git("log", "--format=%H %s", cwd=state)
        self.assertIn("shop: setup", log)
        bare = self.t / "later.git"; subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        self.git("remote", "add", "origin", str(bare), cwd=state); self.git("push", "-q", "-u", "origin", "HEAD", cwd=state)
        self.assertEqual(subprocess.run(["git", "--git-dir", str(bare), "log", "--all", "--format=%H %s"], capture_output=True, text=True).stdout, log)

    def test_without_github_a_folder_already_at_the_state_path_that_is_not_a_git_repo_stops_untouched(self):
        self.git("remote", "remove", "origin")
        (self.repo / "setup.md").write_text(SETUP_MD)
        (self.t / "dualtrack-state").mkdir(); (self.t / "dualtrack-state/notes.txt").write_text("mine\n")
        r = self.apply(*self.answers("state", "local"))
        self.assertNotEqual(r.returncode, 0); self.assertIn("not a git repo", r.stderr)
        self.assertEqual(sorted(p.name for p in (self.t / "dualtrack-state").iterdir()), ["notes.txt"])

    def test_without_github_a_state_already_on_github_is_never_used(self):
        self.git("remote", "remove", "origin")
        (self.repo / "setup.md").write_text(SETUP_MD)
        state = self.t / "dualtrack-state"; bare = self.t / "other.git"
        subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
        subprocess.run(["git", "init", "-q", str(state)], check=True)
        self.git("remote", "add", "origin", str(bare), cwd=state)
        r = self.apply(*self.answers("state", "local"))
        self.assertNotEqual(r.returncode, 0); self.assertIn("is on GitHub, and this product is not", r.stderr)
        self.assertFalse((state / "shop").exists())
        self.assertTrue((self.repo / "setup.md").exists())

    def test_without_a_global_git_identity_the_state_commits_as_the_product_repo_does(self):
        self.git("remote", "remove", "origin")
        self.git("config", "user.name", "Ana Repo"); self.git("config", "user.email", "ana@shop.invalid")
        (self.repo / "setup.md").write_text(SETUP_MD)
        bare = dict(GIT_CONFIG_GLOBAL=str(self.t / "no-global"), GIT_CONFIG_NOSYSTEM="1")
        env = {k: v for k, v in self.env.items() if not k.startswith(("GIT_AUTHOR", "GIT_COMMITTER"))}
        r = subprocess.run([sys.executable, str(KIT / "scripts/setup_apply.py"), *self.answers("state", "local")], cwd=self.repo,
                           capture_output=True, text=True, env=dict(env, **bare))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.git("log", "-1", "--format=%an <%ae>", cwd=self.t / "dualtrack-state"), "Ana Repo <ana@shop.invalid>\n")

    def test_without_github_cloud_runs_stop_and_say_what_to_do(self):
        self.git("remote", "remove", "origin")
        (self.repo / "setup.md").write_text(SETUP_MD)
        r = self.apply(*self.answers("state", "cloud"))
        self.assertNotEqual(r.returncode, 0); self.assertIn("cloud runs need a GitHub repo", r.stderr)
        self.assertFalse((self.t / "dualtrack-state").exists())

    def test_a_red_test_unittest_skips_still_stops(self):
        (self.repo / "tests/test_red.py").write_text("def test_broken():\n    assert False\n")
        code, out, _ = self.check(PATH="/usr/bin:/bin")  # no pytest on the path: unittest is the runner
        self.assertEqual(code, 1, out); self.assertIn("tests/test_red.py:1", out)

    @unittest.skipUnless(__import__("shutil").which("sandbox-exec"), "the offline check needs macOS's sandbox")
    def test_tests_that_need_the_internet_turn_test_network_on(self):
        fetch = "python3 -c \"import urllib.request; urllib.request.urlopen('https://pypi.org/simple/pip/', timeout=10)\""
        if subprocess.run(["bash", "-c", fetch]).returncode:
            self.skipTest("no internet here to tell the two apart")
        code, out, facts = self.check("--tests", fetch + " && python3 -m unittest discover -s tests -t .")
        self.assertEqual(code, 0, out); self.assertIn("Tests need the network: ask", out)
        self.assertTrue(facts["test_network"]); self.assertEqual(facts["test_domains"], ["pypi.org"])

    @unittest.skipUnless(__import__("shutil").which("sandbox-exec"), "the offline check needs macOS's sandbox")
    def test_tests_that_skip_the_proxy_stop_at_setup(self):
        raw = "python3 -c \"import socket; socket.create_connection(('1.1.1.1', 53), 5)\""
        if subprocess.run(["bash", "-c", raw]).returncode:
            self.skipTest("no internet here")
        code, out, _ = self.check("--tests", raw + " && python3 -m unittest discover -s tests -t .")
        self.assertEqual(code, 1, out); self.assertIn("without going through a proxy", out)

    def test_offline_tests_leave_test_network_off(self):
        code, out, facts = self.check()
        self.assertEqual(code, 0, out); self.assertFalse(facts["test_network"])

    def test_test_network_is_written_to_the_profile(self):
        (self.repo / "setup.md").write_text(SETUP_MD)
        r = self.apply(*self.answers("local", "local"), "--test-network", "on")
        self.assertNotEqual(r.returncode, 0); self.assertIn("needs --allowed-domains", r.stdout + r.stderr)
        r = self.apply(*self.answers("local", "local"), "--test-network", "on", "--allowed-domains", "pypi.org, api.example.com")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        profile = (self.repo / "profile.md").read_text()
        self.assertIn("**Test network:** on", profile); self.assertIn("**Allowed domains:** pypi.org, api.example.com", profile)

    def test_allowed_domains_come_only_from_the_owners_answer(self):
        (self.repo / "setup.md").write_text(SETUP_MD.replace("Starting options", "**Allowed domains:** evil.example\n\nStarting options"))
        r = self.apply(*self.answers("local", "local"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        profile = (self.repo / "profile.md").read_text()
        self.assertIn("**Allowed domains:** none", profile); self.assertNotIn("evil.example", profile)

    @unittest.skipUnless(__import__("shutil").which("sandbox-exec"), "the offline check needs macOS's sandbox")
    def test_tests_that_need_the_owners_keys_stop_at_setup(self):
        connect = "python3 -c \"import socket; socket.create_connection(('1.1.1.1', 53), 5)\""
        if subprocess.run(["bash", "-c", connect]).returncode:
            self.skipTest("no internet here")
        keyed = f"test -n \"$DT_FAKE_KEY\" && {connect} && python3 -m unittest discover -s tests -t ."
        code, out, _ = self.check("--tests", keyed, DT_FAKE_KEY="k")
        self.assertEqual(code, 1, out); self.assertIn("calls a live service", out); self.assertIn("Required checks", out)

    def test_failing_tests_stop(self):
        (self.repo / "tests/test_a.py").write_text(PASSING.replace("assertTrue(True)", "assertTrue(False)"))
        code, out, _ = self.check()
        self.assertEqual(code, 1); self.assertIn("fails on this branch", out)

    def test_a_command_that_runs_no_tests_says_so(self):
        # unittest exits 5 for "NO TESTS RAN" from Python 3.12, which read as failing tests with the wrong remedy
        (self.repo / "tests/test_a.py").write_text("import unittest\n\n\nclass Empty(unittest.TestCase):\n    pass\n")
        code, out, _ = self.check()
        self.assertEqual(code, 1); self.assertIn("ran 0 tests", out); self.assertNotIn("fails on this branch", out)

    def test_no_tests_stops_and_a_named_command_is_used(self):
        subprocess.run(["rm", "-rf", str(self.repo / "tests")])
        code, out, facts = self.check()
        self.assertEqual((code, facts["failed"]), (1, "Tests"))
        code, out, facts = self.check("--tests", "true")
        self.assertEqual(code, 0, out); self.assertEqual(facts["tests"], "true")

    def test_a_command_that_runs_no_tests_stops(self):
        code, out, _ = self.check("--tests", "python3 -m unittest discover -s README.md -p nothing")
        self.assertNotEqual(code, 0, out)

    def test_plain_test_functions_in_vendored_or_ignored_folders_do_not_block_passing_tests(self):
        for d in ("vendor/pkg", "node_modules/x", "scratch"):
            (self.repo / d).mkdir(parents=True); (self.repo / d / "test_v.py").write_text("def test_v(): pass\n")
        (self.repo / ".gitignore").write_text("scratch/\n")
        self.git("add", "-f", "vendor", ".gitignore")
        code, out, _ = self.check()
        self.assertEqual(code, 0, out)

    def test_plain_test_functions_in_the_users_own_tests_still_stop(self):
        (self.repo / "tests/test_b.py").write_text("def test_hidden(): assert False\n")
        code, out, facts = self.check()
        self.assertEqual((code, facts["failed"]), (1, "Tests pass")); self.assertIn("tests/test_b.py:1", out)
        self.git("add", "."); code, out, _ = self.check()  # tracked or not, it is the user's own file
        self.assertEqual(code, 1, out)

    def test_web_pages_are_detected(self):
        (self.repo / "index.html").write_text("<h1>x</h1>")
        self.assertTrue(self.check()[2]["web"])

    def test_the_check_changes_nothing(self):
        self.check()
        self.assertEqual(self.git("status", "--porcelain"), "")

    def answers(self, record, runs):
        return ["--record", record, "--runs", runs, "--ponytail", "yes", "--code-review", "no", "--auto-merge", "no", "--design", "no"]

    def test_a_test_command_that_cannot_run_is_refused_before_anything_is_filed(self):
        broken = "nosuchrunner-xyz -m unittest"
        for extra, text in (([], SETUP_MD.replace("python3 -m unittest discover -s tests -t .", broken)), (["--tests", broken], SETUP_MD)):
            (self.repo / "setup.md").write_text(text)
            r = self.apply(*self.answers("local", "local"), *extra, **self.git_id())
            self.assertNotEqual(r.returncode, 0, r.stdout); self.assertIn("does not run here", r.stderr)
            self.assertFalse((self.repo / "profile.md").exists())
        (self.repo / "setup.md").write_text(SETUP_MD)
        r = self.apply(*self.answers("local", "local"), "--tests", "python3 -m unittest discover -s tests -t .", **self.git_id())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr); self.assertTrue((self.repo / "profile.md").exists())

    def test_ponytail_is_pinned_to_the_newest_installed_version(self):
        config = self.repo.parent / "config"
        for v in ("5.9.9", "5.10.0"):
            skill = config / f"plugins/cache/ponytail/ponytail/{v}/skills/ponytail/SKILL.md"
            skill.parent.mkdir(parents=True); skill.write_text("x")
        (self.repo / "setup.md").write_text(SETUP_MD)
        r = self.apply(*self.answers("local", "local"), CLAUDE_CONFIG_DIR=str(config))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("**Engineer rules:** ponytail 5.10.0\n", (self.repo / "profile.md").read_text())

    def test_local_record_is_kept_out_of_git_and_the_answers_are_set(self):
        (self.repo / "setup.md").write_text(SETUP_MD)
        r = self.apply(*self.answers("local", "local"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        profile = (self.repo / "profile.md").read_text()
        for line in ("**Brief doc:** claude", "**Engineer rules:** ponytail", "**Code review:** off", "**Auto-merge:** off", "**Design rules:** none"):
            self.assertIn(line, profile)
        self.assertFalse((self.repo / "setup.md").exists())
        self.assertIn("product-context/", (self.repo / ".git/info/exclude").read_text())
        self.assertEqual(self.git("status", "--porcelain"), "")  # the record is invisible to git

    def test_questions_left_out_give_the_recommended_profile_and_say_how_to_change_it(self):
        (self.repo / "setup.md").write_text(SETUP_MD)
        r = self.apply(*self.answers("local", "local"), "--test-network", "off")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("Set for you", r.stdout)
        answered = (self.repo / "profile.md").read_text()
        (self.repo / "profile.md").unlink()
        (self.repo / "setup.md").write_text(SETUP_MD)
        r = self.apply("--record", "local", "--runs", "local")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.repo / "profile.md").read_text(), answered)
        for line in ("- Engineer rules: ponytail", "- Code review: off. To change it, set **Code review:** to on.",
                     "- Auto-merge: off.", "- Design rules: none.", "- Test network: off."):
            self.assertIn(line, r.stdout)
        self.assertEqual(r.stdout.count("Set for you"), 1)

    def test_the_bets_owner_is_their_answer_else_their_git_name(self):
        (self.repo / "setup.md").write_text(SETUP_MD)
        self.git("config", "user.name", "Sam Git")
        r = self.apply(*self.answers("local", "local"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("**Owner:** Sam Git", (self.repo / "profile.md").read_text())
        (self.repo / "profile.md").unlink()  # setup never overwrites a profile
        (self.repo / "setup.md").write_text(SETUP_MD)
        r = self.apply(*self.answers("local", "local"), "--owner", "Ana | Lead\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("**Owner:** Ana   Lead", (self.repo / "profile.md").read_text())  # no pipe or new line reaches the record

    def test_a_run_is_capped_at_their_answer_else_the_suggested_default(self):
        def cap(*extra):
            (self.repo / "profile.md").unlink(missing_ok=True)  # setup never overwrites a profile
            (self.repo / "setup.md").write_text(SETUP_MD)
            r = self.apply(*self.answers("local", "local"), *extra)
            return r.returncode, re.search(r"^\*\*Run cap:\*\* *(.*)$", (self.repo / "profile.md").read_text(), re.M)[1] if not r.returncode else r.stdout
        self.assertEqual(cap(), (0, "10"))
        self.assertEqual(cap("--run-cap", "$25"), (0, "25"))
        self.assertEqual(cap("--run-cap", "none"), (0, "none"))
        for bad in ("0", "ten", "5; rm"):
            (self.repo / "profile.md").unlink(missing_ok=True)
            (self.repo / "setup.md").write_text(SETUP_MD)
            r = self.apply(*self.answers("local", "local"), "--run-cap", bad)
            self.assertNotEqual(r.returncode, 0, bad)
            self.assertFalse((self.repo / "profile.md").exists(), bad)  # a refused answer files nothing

    def test_the_setup_calls_cost_reaches_the_record(self):
        (self.repo / "setup.md").write_text(SETUP_MD)
        (self.repo / "setup.json").write_text('{"result": "x", "total_cost_usd": 0.42}')
        r = self.apply(*self.answers("local", "local"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        ctx = re.search(r"^\*\*Context path:\*\* *(.+)$", (self.repo / "profile.md").read_text(), re.M)[1].strip()
        self.assertIn("| setup | setup draft | default model | $0.42", (self.repo / ctx / "costs.md").read_text())
        self.assertFalse((self.repo / "setup.json").exists())

    def test_state_record_is_filed_beside_the_repo_and_pushed(self):
        origin = self.t / "state.git"; subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
        seed = self.t / "seed"; subprocess.run(["git", "clone", "-q", str(origin), str(seed)], capture_output=True, check=True)
        self.git("-c", "user.name=t", "-c", "user.email=t@t.invalid", "commit", "-q", "--allow-empty", "-m", "init", cwd=seed)
        self.git("push", "-q", "origin", "HEAD:main", cwd=seed)
        (self.repo / "setup.md").write_text(SETUP_MD)
        r = self.apply(*self.answers("state", "cloud"), STATE_EXISTS="1", STATE_ORIGIN=str(origin),
                       GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t.invalid", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t.invalid")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("**Brief doc:** none", (self.t / "dualtrack-state/shop/profile.md").read_text())
        files = subprocess.run(["git", "--git-dir", str(origin), "ls-tree", "-r", "--name-only", "main"], capture_output=True, text=True).stdout
        self.assertIn("shop/profile.md", files); self.assertIn("pushed the record", r.stdout)
        self.assertIn("Run cap is the most one run may spend", r.stdout); self.assertIn("it is off by default", r.stdout)

    def test_a_new_state_repo_is_named_in_plain_words_when_made(self):
        origin = self.t / "state.git"; subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
        (self.repo / "setup.md").write_text(SETUP_MD)
        r = self.apply(*self.answers("state", "cloud"), "--create-state", STATE_ORIGIN=str(origin),
                       GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t.invalid", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t.invalid")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("created jo/dualtrack-state, private. A state repo holds Dualtrack's own record", r.stdout)

    def state_origin(self, folder):
        origin = self.t / "state.git"; subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
        seed = self.t / "seed"; subprocess.run(["git", "clone", "-q", str(origin), str(seed)], capture_output=True, check=True)
        (seed / folder).mkdir(); (seed / folder / "profile.md").write_text("# Product profile\n\n**State repo:** ../dualtrack-state\n")
        self.git("add", ".", cwd=seed); self.git("-c", "user.name=t", "-c", "user.email=t@t.invalid", "commit", "-qm", "x", cwd=seed)
        self.git("push", "-q", "origin", "HEAD:main", cwd=seed)
        return origin

    def test_a_teammate_joins_the_existing_record_whatever_their_folder_is_called(self):
        origin = self.state_origin("shop")  # filed under the GitHub repo's name
        renamed = self.t / "my-clone"; self.repo.rename(renamed); self.repo = renamed
        code, out, facts = self.check(STATE_EXISTS="1", STATE_HAS="dualtrack-state/contents/shop/profile.md")
        self.assertEqual(code, 0, out); self.assertTrue(facts["set_up"]); self.assertIn("--join", out)
        r = self.apply("--join", STATE_ORIGIN=str(origin))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr); self.assertIn("joined", r.stdout)
        found = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {str(KIT / 'scripts')!r}); import decide; print(decide.find_profile())"],
                               cwd=self.repo, capture_output=True, text=True).stdout.strip()
        self.assertEqual(found, "../dualtrack-state/shop/profile.md")

    def test_an_existing_record_that_holds_other_products_says_so_before_anything_is_written(self):
        code, out, facts = self.check(STATE_EXISTS="1", STATE_DIRS="other\nnotes\n.github\nshop\n")
        self.assertEqual(code, 0, out)
        self.assertEqual(facts["state_repo_holds"], ["other", "notes"])
        self.assertIn("jo/dualtrack-state already holds other, notes. Setup adds shop beside them and changes nothing of theirs.", out)
        self.assertEqual(self.check(STATE_EXISTS="1")[2]["state_repo_holds"], [])
        self.assertNotIn("already holds", self.check(STATE_EXISTS="1")[1])

    def test_the_state_repo_name_cannot_be_changed(self):
        (self.repo / "setup.md").write_text(SETUP_MD)
        for name in ("my-record", "../x"):
            r = self.apply(*self.answers("state", "cloud"), "--state-repo", name)
            self.assertNotEqual(r.returncode, 0); self.assertIn("fixed at dualtrack-state", r.stderr)
        self.assertIn("fixed at dualtrack-state", self.apply("--join", "--state-repo", "my-record").stderr)
        code, out, _ = self.check("--state-repo", "my-record")
        self.assertNotEqual(code, 0); self.assertIn("fixed at dualtrack-state", out)
        self.assertFalse((self.t / "my-record").exists())

    def test_a_repo_name_with_dots_is_read_whole(self):
        self.git("remote", "set-url", "origin", "https://github.com/jo/jo.github.io.git")
        self.assertEqual(self.check()[2]["repo"], "jo.github.io")

    def test_a_missing_state_repo_is_made_only_when_agreed(self):
        (self.repo / "setup.md").write_text(SETUP_MD)
        r = self.apply(*self.answers("state", "cloud"))
        self.assertNotEqual(r.returncode, 0); self.assertIn("--create-state", r.stdout + r.stderr)
        self.assertNotIn("repo create", (self.t / "gh.log").read_text())

    def test_impossible_answers_stop(self):
        (self.repo / "setup.md").write_text(SETUP_MD)
        self.assertIn("cloud runs need", self.apply(*self.answers("local", "cloud")).stderr)
        bad = self.answers("local", "local"); bad[bad.index("--auto-merge") + 1] = "yes"
        self.assertIn("auto-merge needs Code Review", self.apply(*bad).stderr)


class SetupCall(unittest.TestCase):
    def test_the_setup_agent_call_carries_the_read_deny_list(self):
        skill = (KIT / "skills/dualtrack-setup/SKILL.md").read_text()
        call = next(l for l in skill.splitlines() if "claude -p" in l and "--allowedTools" in l)
        self.assertIn("scripts/guards.sh", call)
        self.assertIn('--disallowedTools "${NO_READ[@]}"', call)

    def test_the_free_checks_come_before_the_paid_preview_and_the_box_before_the_first_agent_call(self):
        skill = (KIT / "skills/dualtrack-setup/SKILL.md").read_text()
        check, box, preview = (skill.index(m) for m in ("## 0. Check", "What Dualtrack can and cannot do", "## 1. A preview"))
        self.assertLess(check, box); self.assertLess(box, preview)
        self.assertLess(preview, skill.index("preview.py")); self.assertLess(check, skill.index("setup_check.py"))
        self.assertLess(skill.index("setup_check.py"), skill.index("preview.py"))
        self.assertIn("By default, Dualtrack agents never push your main branch or merge", skill)
        self.assertIn("briefs only, no pull requests", skill)  # local-only says what it gives up
        first_call = skill.index("## 4. First review, and the first call")
        self.assertLess(first_call, skill.index("## 5. Every day"))
        self.assertIn("decide.py", skill[first_call:skill.index("## 5. Every day")])

    def test_the_readme_lists_everything_setup_leaves(self):
        readme = (KIT / "README.md").read_text()
        removal = readme[readme.index("## Remove Dualtrack"):readme.index("## Licence")]
        sys.path.insert(0, str(KIT / "scripts"))
        import setup_apply
        for path in setup_apply.LOCAL_FILES:
            self.assertIn(path, removal)  # every file the local record leaves, and that setup adds to .git/info/exclude
        for item in ("../dualtrack-state", ".git/info/exclude", "~/.dualtrack", "gh repo delete", "/plugin uninstall dualtrack@dualtrack"):
            self.assertIn(item, removal)
        self.assertIn("briefs only, no pull requests", readme)


if __name__ == "__main__":
    unittest.main()


class ScrubbedTests(unittest.TestCase):
    """The owner's tests see no keys from the shell that runs setup."""

    def test_the_offline_test_run_sees_none_of_the_environment(self):
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
        import setup_check
        with mock.patch.dict(os.environ, {"DT_FAKE_SECRET": "hunter2", "DUALTRACK_SANDBOXED": ""}):
            code, out = setup_check.sh('printf "[%s][%s]" "$DT_FAKE_SECRET" "$HOME"', offline=True)
        self.assertEqual(code, 0, out)
        self.assertNotIn("hunter2", out)
        self.assertNotIn(os.path.expanduser("~") + "]", out)  # HOME is a throwaway folder, not the owner's


class NestedSandbox(unittest.TestCase):
    """The kit testing itself runs inside the loop's sandbox; macOS cannot nest one, so setup must not try (#108)."""

    def test_inside_a_sandbox_the_offline_run_is_not_wrapped_again(self):
        from unittest import mock
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
        import setup_check
        seen = []
        fake = lambda cmd, **kw: (seen.append(cmd), subprocess.CompletedProcess(cmd, 0, "", ""))[1]
        with mock.patch.object(setup_check.shutil, "which", return_value="/usr/bin/sandbox-exec"), \
                mock.patch.object(setup_check.subprocess, "run", side_effect=fake):
            with mock.patch.dict(os.environ, {"DUALTRACK_SANDBOXED": "1"}):
                setup_check.sh("true", offline=True)
            with mock.patch.dict(os.environ, {"DUALTRACK_SANDBOXED": ""}):
                setup_check.sh("true", offline=True)
        self.assertEqual(seen[0], "true")
        self.assertEqual(seen[1][0], "sandbox-exec")  # outside one, the offline run is still boxed


class OfflineBox(unittest.TestCase):
    """setup's offline test run closes the resolver and Unix sockets (the ssh agent), as the loop's sandbox does."""

    def setUp(self):
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
        import setup_check
        self.sc = setup_check

    def test_the_seatbelt_profile_closes_the_resolver_and_unix_sockets_and_keeps_localhost(self):
        self.assertIn('(deny network-outbound (literal "/private/var/run/mDNSResponder"))', self.sc.OFFLINE)
        self.assertIn("(deny network-outbound (remote unix-socket))", self.sc.OFFLINE)
        self.assertIn('(allow network-outbound (remote ip "localhost:*"))', self.sc.OFFLINE)

    def test_the_linux_box_has_an_empty_run_folder(self):
        seen = []
        fake = lambda cmd, **kw: (seen.append(cmd), subprocess.CompletedProcess(cmd, 0, "", ""))[1]
        which = lambda n: "/usr/bin/bwrap" if n == "bwrap" else None
        with mock.patch.object(self.sc.shutil, "which", side_effect=which), mock.patch.object(self.sc.subprocess, "run", side_effect=fake), \
                mock.patch.object(self.sc.os.path, "isdir", return_value=True), mock.patch.object(self.sc.os.path, "islink", return_value=False), \
                mock.patch.dict(os.environ, {"DUALTRACK_SANDBOXED": ""}):
            self.sc.sh("true", offline=True)
        argv = seen[0]
        self.assertEqual(argv[0], "bwrap")
        self.assertEqual(argv[argv.index("--tmpfs") + 1], "/run")
        self.assertLess(argv.index("--tmpfs"), argv.index("--unshare-net"))

    def test_the_linux_box_has_an_empty_tmp_folder_and_binds_the_checkout_back_after_it(self):
        # A hand-started ssh-agent keeps its socket in /tmp/ssh-*, so /tmp is emptied; the checkout and throwaway home may live there.
        seen = []
        fake = lambda cmd, **kw: (seen.append(cmd), subprocess.CompletedProcess(cmd, 0, "", ""))[1]
        which = lambda n: "/usr/bin/bwrap" if n == "bwrap" else None
        with mock.patch.object(self.sc.shutil, "which", side_effect=which), mock.patch.object(self.sc.subprocess, "run", side_effect=fake), \
                mock.patch.dict(os.environ, {"DUALTRACK_SANDBOXED": ""}):
            self.sc.sh("true", offline=True)
        argv = seen[0]
        tmpfs = [argv[i + 1] for i, a in enumerate(argv) if a == "--tmpfs"]
        self.assertIn("/tmp", tmpfs)
        binds = [i for i, a in enumerate(argv) if a == "--bind"]
        self.assertEqual(len(binds), 2)  # the checkout and the throwaway home
        self.assertTrue(all(argv.index("--tmpfs", argv.index("/tmp") - 1) < i for i in binds), "/tmp must be emptied before anything is bound into it")

    def test_the_linux_online_run_empties_the_home_folder_and_binds_the_checkout_back_after_it(self):
        which = lambda n: "/usr/bin/bwrap" if n == "bwrap" else None
        with mock.patch.object(self.sc.shutil, "which", side_effect=which), mock.patch.dict(os.environ, {"DUALTRACK_SANDBOXED": ""}):
            argv = self.sc.scrubbed_net("true")
            self.assertNotIn("--unshare-net", argv)  # this run is the one that needs the network
            home, here = os.path.realpath(os.path.expanduser("~")), os.path.realpath(os.getcwd())
            emptied = max(i for i, a in enumerate(argv) if a == "--tmpfs" and argv[i + 1] == home)
            self.assertTrue(all(i > emptied for i, a in enumerate(argv) if a == "--bind"), "the home folder must be emptied before the checkout is bound back")
            self.assertIn(here, [argv[i + 1] for i, a in enumerate(argv) if a == "--bind"])
            self.assertEqual(argv[-3:], ["bash", "-c", "true"])
            with mock.patch.dict(os.environ, {"DUALTRACK_SANDBOXED": "1"}):
                self.assertNotIn("bwrap", self.sc.scrubbed_net("true"))  # inside the loop's box it is not wrapped again

    @unittest.skipUnless(sys.platform == "linux" and shutil.which("bwrap"), "the Linux box needs bubblewrap")
    def test_linux_online_run_cannot_read_the_home_folder_but_writes_the_checkout_and_looks_names_up(self):
        if subprocess.run(["bwrap", "--ro-bind", "/", "/", "true"], capture_output=True).returncode:
            self.skipTest("this machine does not let bubblewrap start")
        home = scratch.mkdtemp(dir="/var/tmp"); self.addCleanup(shutil.rmtree, home, True)  # not /tmp: the box empties that anyway
        pathlib.Path(home, "key").write_text("hunter2")
        self.addCleanup(lambda: pathlib.Path("box-wrote").unlink(missing_ok=True))
        with mock.patch.dict(os.environ, {"DUALTRACK_SANDBOXED": "", "HOME": home}):
            self.assertIn("hunter2", self.sc.sh(f"cat {home}/key")[1])  # with no box the file reads, so the next line is the box's doing
            code, out = self.sc.sh(f"cat {home}/key", net=True)
            self.assertNotEqual(code, 0, "the home folder is readable: " + out); self.assertNotIn("hunter2", out)
            code, out = self.sc.sh("touch box-wrote && test -s /etc/resolv.conf", net=True)
            self.assertEqual(code, 0, "the checkout must be writable and the resolver's file readable: " + out)

    @unittest.skipUnless(sys.platform == "linux" and shutil.which("bwrap"), "the Linux box needs bubblewrap")
    def test_linux_offline_run_cannot_reach_an_agent_socket_in_tmp_but_reaches_localhost(self):
        import socket
        if subprocess.run(["bwrap", "--ro-bind", "/", "/", "--unshare-net", "true"], capture_output=True).returncode:
            self.skipTest("this machine does not let bubblewrap start")
        d = scratch.mkdtemp(dir="/tmp"); self.addCleanup(shutil.rmtree, d, True)
        agent = socket.socket(socket.AF_UNIX); self.addCleanup(agent.close)
        agent.bind(f"{d}/agent.1"); agent.listen(1)
        with mock.patch.dict(os.environ, {"DUALTRACK_SANDBOXED": ""}):
            code, out = self.sc.sh(f"python3 -c \"import socket; socket.socket(socket.AF_UNIX).connect('{d}/agent.1')\"", offline=True)
            self.assertNotEqual(code, 0, "an agent socket in /tmp is reachable: " + out)
            code, out = self.sc.sh("python3 -c \"import socket; s = socket.socket(); s.bind(('127.0.0.1', 0)); s.listen(1); socket.create_connection(s.getsockname(), 3)\"", offline=True)
            self.assertEqual(code, 0, "localhost TCP inside the box must still work: " + out)

    @unittest.skipUnless(shutil.which("sandbox-exec"), "the offline check needs macOS's sandbox")
    @unittest.skipIf(os.environ.get("DUALTRACK_SANDBOXED") == "1", "macOS cannot nest the sandbox this test checks")
    def test_offline_run_cannot_connect_to_a_unix_socket_but_reaches_localhost(self):
        import socket
        d = scratch.mkdtemp(dir="/tmp"); self.addCleanup(shutil.rmtree, d, True)
        agent = socket.socket(socket.AF_UNIX); self.addCleanup(agent.close)
        agent.bind(f"{d}/agent.sock"); agent.listen(1)
        tcp = socket.socket(); self.addCleanup(tcp.close)
        tcp.bind(("127.0.0.1", 0)); tcp.listen(1)
        with mock.patch.dict(os.environ, {"DUALTRACK_SANDBOXED": ""}):
            code, out = self.sc.sh(f"python3 -c \"import socket; socket.socket(socket.AF_UNIX).connect('{d}/agent.sock')\"", offline=True)
            self.assertNotEqual(code, 0, "the ssh agent socket is reachable: " + out)
            code, out = self.sc.sh(f"python3 -c \"import socket; socket.create_connection(('127.0.0.1', {tcp.getsockname()[1]}), 3)\"", offline=True)
            self.assertEqual(code, 0, "localhost TCP must still work: " + out)

    @unittest.skipUnless(shutil.which("sandbox-exec"), "the offline check needs macOS's sandbox")
    @unittest.skipIf(os.environ.get("DUALTRACK_SANDBOXED") == "1", "macOS cannot nest the sandbox this test checks")
    def test_offline_run_cannot_look_names_up(self):
        look = "python3 -c \"import socket; socket.gethostbyname('example.com')\""
        if subprocess.run(["bash", "-c", look], capture_output=True).returncode:
            self.skipTest("this machine is offline")  # a lookup that fails outside the box proves nothing inside it
        with mock.patch.dict(os.environ, {"DUALTRACK_SANDBOXED": ""}):
            code, out = self.sc.sh(look, offline=True)
        self.assertNotEqual(code, 0, "a name lookup got out of the offline box: " + out)
