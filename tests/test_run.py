"""run.sh and file_setup.py, with a fake claude."""
import os, pathlib, shutil, stat, subprocess, sys, time, unittest
try:
    import scratch
except ImportError:  # run as tests.test_x from the repo root
    from tests import scratch

KIT = pathlib.Path(__file__).resolve().parent.parent
MEMO = """Product manager memo, 2026-10-30: gaps
Mode: acquisition
Cadence: weekly

Recommendation:
A page
Move: Reach
Score: reach 3, evidence 3, effort 3, goal link 3
Goal link: readers go to the page, then sign up
Verdict: confirmed
Why: public evidence
Moves: sign-ups
Done when: it exists
Size: small

Bets:
- proposed new idea: a page | Evidence: "I could not find the price" | 3 signals | support inbox 2026-11-02; survey 2026-11-04; session notes 2026-11-09

New ideas:
- A page: audience, promise

Record:
- decisions: A page | proposed
"""
FAKE = """#!/usr/bin/env python3
import json, sys
open("PROMPTS", "a").write(sys.argv[2] + "\\n")
import os, subprocess, time
os.environ.get("HOOK") and subprocess.run(["bash", os.environ["HOOK"]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # another machine, mid-run
os.environ.get("SLEEP") and time.sleep(float(os.environ["SLEEP"]))
os.environ.get("ARGS_LOG") and open(os.environ["ARGS_LOG"], "a").write(" ".join(sys.argv) + "\\n")
print(json.dumps({"result": MEMO, "total_cost_usd": 0.01}))
"""


class Run(unittest.TestCase):
    def setUp(self):
        self.t = pathlib.Path(scratch.mkdtemp())
        fake = self.t / "claude"
        fake.write_text(FAKE.replace("MEMO", repr(MEMO)).replace("PROMPTS", str(self.t / "prompts")))
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        (self.t / "setup.md").write_text("# Product profile\n\n**Mode:** unknown\n\n**New idea slots:** 1\n\n"
                                         "**Run cap:** 5\n\nStarting options:\n- Reach: x\n\nOpen questions:\n1. y\n")

    def setup_agent(self):
        return subprocess.run([sys.executable, str(KIT / "scripts/file_setup.py"), "setup.md"], cwd=self.t,
                              capture_output=True, text=True)

    def test_a_run_from_a_subfolder_saves_to_the_state_repo_not_the_product_repo(self):
        # Sweep 2026-11-12: from a subfolder, ../state resolved inside the product repo and the record was pushed there.
        origin = self.t / "state.git"; subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
        state = self.t / "state"; subprocess.run(["git", "clone", "-q", str(origin), str(state)], capture_output=True, check=True)
        for c in (["config", "user.name", "t"], ["config", "user.email", "t@t.invalid"], ["checkout", "-q", "-b", "main"],
                  ["commit", "-q", "--allow-empty", "-m", "init"], ["push", "-q", "-u", "origin", "main"]):
            subprocess.run(["git", "-C", str(state), *c], capture_output=True, check=True)
        repo = self.t / "shop"; repo.mkdir()
        (repo / "setup.md").write_text((self.t / "setup.md").read_text())
        subprocess.run([sys.executable, str(KIT / "scripts/file_setup.py"), "setup.md", "--state", "../state"], cwd=repo, check=True)
        for c in (["init", "-q", "-b", "main"], ["config", "user.name", "t"], ["config", "user.email", "t@t.invalid"],
                  ["add", "setup.md"], ["commit", "-qm", "init"]):
            subprocess.run(["git", "-C", str(repo), *c], capture_output=True, check=True)
        (repo / "sub").mkdir()
        r = subprocess.run(["bash", str(KIT / "scripts/run.sh"), "../../state/shop/profile.md"], cwd=repo / "sub",
                           capture_output=True, text=True, env=dict(os.environ, CLAUDE=str(self.t / "claude")))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        files = subprocess.run(["git", "--git-dir", str(origin), "ls-tree", "-r", "--name-only", "main"], capture_output=True, text=True).stdout
        self.assertIn("shop/product-context/morning.md", files, r.stdout)
        self.assertFalse((repo / "sub/state").exists()); self.assertFalse((repo / "state").exists())


    def test_the_record_is_never_saved_into_a_folder_inside_another_repo(self):
        repo = self.t / "shop"; (repo / "state/shop/product-context").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        r = subprocess.run(["bash", "-c", f'. "{KIT}/scripts/guards.sh"; state_save "$1/state/shop/product-context" "$1/state" msg; echo "rc $?"',
                            "x", str(repo)], capture_output=True, text=True)
        self.assertIn("state not saved", r.stdout); self.assertIn("rc 1", r.stdout)
        (repo / "state/shop/product-context/memo.md").write_text("private\n")
        subprocess.run(["bash", "-c", f'. "{KIT}/scripts/guards.sh"; state_save "$1/state/shop/product-context" "$1/state" msg', "x", str(repo)],
                       capture_output=True)
        self.assertEqual(subprocess.run(["git", "-C", str(repo), "diff", "--cached", "--name-only"], capture_output=True, text=True).stdout, "")
        self.assertNotEqual(subprocess.run(["git", "-C", str(repo), "rev-parse", "-q", "--verify", "HEAD"], capture_output=True).returncode, 0)

    def test_a_state_push_that_never_answers_is_cut_off_and_names_the_next_step(self):
        import time
        origin = self.t / "state.git"; subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
        state = self.t / "state"; subprocess.run(["git", "clone", "-q", str(origin), str(state)], capture_output=True, check=True)
        for c in (["config", "user.name", "t"], ["config", "user.email", "t@t.invalid"], ["checkout", "-q", "-b", "main"],
                  ["commit", "-q", "--allow-empty", "-m", "init"], ["push", "-q", "-u", "origin", "main"]):
            subprocess.run(["git", "-C", str(state), *c], capture_output=True, check=True)
        (state / "shop").mkdir(); (state / "shop/memo.md").write_text("x\n")
        shim = self.t / "shim"; shim.mkdir()
        (shim / "git").write_text(f'#!/bin/bash\nfor a; do [ "$a" = push ] && exec sleep 60; done\nexec {shutil.which("git")} "$@"\n')
        (shim / "git").chmod(0o755)
        call = ["bash", "-c", f'. "{KIT}/scripts/guards.sh"; state_save "$1/shop" "$1" msg; echo "rc $?"; echo "$STATE_MSG"', "x", str(state)]
        t0 = time.time()
        r = subprocess.run(call, capture_output=True, text=True, env=dict(os.environ, PATH=f"{shim}:{os.environ['PATH']}", NET_TIMEOUT="2"))
        self.assertLess(time.time() - t0, 30); self.assertIn("rc 1", r.stdout)
        self.assertIn("state not saved: the record is committed", r.stdout); self.assertIn("run: git -C", r.stdout)
        (state / "shop/memo.md").write_text("y\n")  # the same call, with a git that answers
        r = subprocess.run(call, capture_output=True, text=True, env=dict(os.environ, NET_TIMEOUT="30"))
        self.assertIn("rc 0", r.stdout, r.stdout + r.stderr)

    def test_setup_is_ready_to_run(self):
        self.assertEqual(self.setup_agent().returncode, 0)
        profile = (self.t / "profile.md").read_text()
        self.assertIn("**Mode:** acquisition", profile); self.assertIn("**Context store:** local", profile)
        self.assertNotIn("Starting options", profile)
        self.assertIn("Starting options", (self.t / "setup-notes.md").read_text())
        self.assertTrue((self.t / "product-context/decisions.md").is_file())

    def test_two_products_share_one_state_repo_and_leave_their_repos_clean(self):
        for name in ("shop", "blog"):
            repo = self.t / name; repo.mkdir()
            (repo / "setup.md").write_text((self.t / "setup.md").read_text())
            r = subprocess.run([sys.executable, str(KIT / "scripts/file_setup.py"), "setup.md", "--state", "../state"],
                               cwd=repo, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(sorted(p.name for p in repo.iterdir()), ["setup.md"])
            profile = (self.t / "state" / name / "profile.md").read_text()
            self.assertIn(f"**Context path:** ../state/{name}/product-context", profile)
            self.assertIn(f"**Numbers file:** ../state/{name}/numbers.md", profile)
            self.assertIn("**State repo:** ../state", profile)
            self.assertTrue((self.t / "state" / name / "product-context/decisions.md").is_file())

    def test_setup_keeps_only_commands(self):
        import sys; sys.path.insert(0, str(KIT / "scripts"))
        from file_setup import runnable_tests
        out = runnable_tests("**Test commands:** `npm test` (coverage), `npx tsc --noEmit` for types (inferred: `build` is `tsc`).\n")
        self.assertIn("**Test commands:** npm test && npx tsc --noEmit\n", out)

    def test_setup_never_overwrites(self):
        (self.t / "profile.md").write_text("mine")
        self.assertEqual(self.setup_agent().returncode, 2)
        self.assertEqual((self.t / "profile.md").read_text(), "mine")

    def run_weekly(self, **env):
        self.setup_agent()
        return dict(args=["bash", str(KIT / "scripts/run.sh"), "profile.md"], cwd=self.t, text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, env=dict(os.environ, CLAUDE=str(self.t / "claude"), **env))

    def team_log(self):
        return (self.t / "product-context/team-log.md").read_text()

    def test_a_run_stopped_by_the_cost_cap_leaves_a_team_log_line_with_its_spend(self):
        r = subprocess.run(**self.run_weekly(COST_CAP="0.015"))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertRegex(self.team_log(), r"- \d{4}-\d\d-\d\d \| stopped early, over the \$0\.015 cap at \w+ \| \$0\.0\d")
        self.assertEqual(self.team_log().count("stopped early"), 1)

    def test_a_killed_run_leaves_a_team_log_line(self):
        p = subprocess.Popen(**self.run_weekly(SLEEP="30"))
        for _ in range(600):
            if (self.t / "prompts").exists(): break
            time.sleep(0.1)
        self.assertTrue((self.t / "prompts").exists(), "the first step never started")
        p.terminate(); p.communicate(timeout=60)
        self.assertRegex(self.team_log(), r"- \d{4}-\d\d-\d\d \| stopped early, run ended before it finished \| \$0")

    def test_a_finished_run_logs_once_and_not_as_stopped(self):
        r = subprocess.run(**self.run_weekly())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("stopped early", self.team_log()); self.assertEqual(self.team_log().count("weekly review"), 1)

    def test_run_has_every_step_and_files(self):
        self.setup_agent()
        r = subprocess.run(["bash", str(KIT / "scripts/run.sh"), "profile.md"], cwd=self.t, capture_output=True, text=True,
                           env=dict(os.environ, CLAUDE=str(self.t / "claude")))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        prompts = (self.t / "prompts").read_text()
        for step in ("Step: research", "Step: new ideas", "Step: disprove", "Step: decide"):
            self.assertIn(step, prompts)
        self.assertIn(str(KIT / "moves.md"), prompts)
        self.assertTrue(list((self.t / "product-context/memos").glob("*.md")))
        # The review's cost reaches the team log and the brief, so weekly runs are counted too.
        self.assertRegex((self.t / "product-context/team-log.md").read_text(), r"- \d{4}-\d{2}-\d{2} \| weekly review filed \| \$[0-9.]+")
        self.assertIn("**Cost (estimated usage):**", (self.t / "product-context/morning.md").read_text())

    def test_a_state_repo_run_files_where_the_loop_reads(self):
        # Paths in a state-repo profile are relative to the product repo: the first run must file there too.
        repo, _ = self.state_scene()  # a real state repo: a record that cannot be pushed fails the run
        r = subprocess.run(["bash", str(KIT / "scripts/run.sh"), "../state/shop/profile.md"], cwd=repo, capture_output=True,
                           text=True, env=dict(os.environ, CLAUDE=str(self.t / "claude")))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(list((self.t / "state/shop/product-context/memos").glob("*.md")))
        self.assertFalse((self.t / "state/shop/state").exists())

    def test_a_first_run_pushes_its_record_to_the_state_repo(self):
        origin = self.t / "state.git"; subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
        state = self.t / "state"; subprocess.run(["git", "clone", "-q", str(origin), str(state)], capture_output=True, check=True)
        for c in (["config", "user.name", "t"], ["config", "user.email", "t@t.invalid"], ["checkout", "-q", "-b", "main"],
                  ["commit", "-q", "--allow-empty", "-m", "init"], ["push", "-q", "-u", "origin", "main"]):
            subprocess.run(["git", "-C", str(state), *c], capture_output=True, check=True)
        repo = self.t / "shop"; repo.mkdir()
        (repo / "setup.md").write_text((self.t / "setup.md").read_text())
        subprocess.run([sys.executable, str(KIT / "scripts/file_setup.py"), "setup.md", "--state", "../state"], cwd=repo, check=True)
        r = subprocess.run(["bash", str(KIT / "scripts/run.sh"), "../state/shop/profile.md"], cwd=repo, capture_output=True,
                           text=True, env=dict(os.environ, CLAUDE=str(self.t / "claude")))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        files = subprocess.run(["git", "--git-dir", str(origin), "ls-tree", "-r", "--name-only", "main"], capture_output=True, text=True).stdout
        self.assertIn("shop/product-context/morning.md", files, r.stdout)
        self.assertRegex(files, r"shop/product-context/memos/.+\.md")

    def test_a_first_run_with_dualtrack_state_on_this_machine_only_commits_its_record(self):
        state = self.t / "state"; subprocess.run(["git", "init", "-q", "-b", "main", str(state)], check=True)
        repo = self.t / "shop"; repo.mkdir(); subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / "setup.md").write_text((self.t / "setup.md").read_text())
        subprocess.run([sys.executable, str(KIT / "scripts/file_setup.py"), "setup.md", "--state", "../state"], cwd=repo, check=True)
        r = subprocess.run(["bash", str(KIT / "scripts/run.sh"), "../state/shop/profile.md"], cwd=repo, capture_output=True, text=True,
                           env=dict(os.environ, CLAUDE=str(self.t / "claude"), GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t.invalid",
                                    GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t.invalid"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr); self.assertNotIn("not saved", r.stdout)
        files = subprocess.run(["git", "-C", str(state), "ls-tree", "-r", "--name-only", "HEAD"], capture_output=True, text=True).stdout
        self.assertIn("shop/product-context/morning.md", files, r.stdout)

    def state_scene(self):
        origin = self.t / "state.git"; subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
        state = self.t / "state"; subprocess.run(["git", "clone", "-q", str(origin), str(state)], capture_output=True, check=True)
        for c in (["config", "user.name", "t"], ["config", "user.email", "t@t.invalid"], ["checkout", "-q", "-b", "main"],
                  ["commit", "-q", "--allow-empty", "-m", "init"], ["push", "-q", "-u", "origin", "main"]):
            subprocess.run(["git", "-C", str(state), *c], capture_output=True, check=True)
        repo = self.t / "shop"; repo.mkdir()
        (repo / "setup.md").write_text((self.t / "setup.md").read_text())
        subprocess.run([sys.executable, str(KIT / "scripts/file_setup.py"), "setup.md", "--state", "../state"], cwd=repo, check=True)
        return repo, state

    def run_sh(self, repo, **env):
        return dict(args=["bash", str(KIT / "scripts/run.sh"), "../state/shop/profile.md"], cwd=repo, text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, env=dict(os.environ, CLAUDE=str(self.t / "claude"), **env))

    def test_a_record_the_state_repo_refuses_fails_the_run(self):
        repo, state = self.state_scene()
        other = self.t / "other"
        subprocess.run(["git", "clone", "-q", str(self.t / "state.git"), str(other)], capture_output=True, check=True)
        (other / "shop/product-context").mkdir(parents=True); (other / "shop/product-context/morning.md").write_text("another machine\n")
        hook = self.t / "hook.sh"
        hook.write_text(f"cd {other} && git -c user.name=o -c user.email=o@o.invalid commit -qam x 2>/dev/null; "
                        f"git add -A && git -c user.name=o -c user.email=o@o.invalid commit -qm other && git push -q\n")
        r = subprocess.run(**self.run_sh(repo, HOOK=str(hook)))
        lines = r.stdout.strip().splitlines()
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("not saved", lines[-1]); self.assertIn("git -C", lines[-1])
        self.assertFalse((state / ".git/rebase-merge").exists() or (state / ".git/rebase-apply").exists(), "left mid-rebase")
        self.assertEqual(subprocess.run(["git", "-C", str(state), "symbolic-ref", "-q", "HEAD"], capture_output=True).returncode, 0, "detached")

    def test_a_second_run_at_once_stops_instead_of_losing_its_record(self):
        repo, state = self.state_scene()
        first = subprocess.Popen(**self.run_sh(repo, SLEEP="1"))
        for _ in range(100):
            if (self.t / "prompts").exists(): break
            time.sleep(0.1)
        second = subprocess.run(**self.run_sh(repo))
        out1, _ = first.communicate()
        self.assertEqual(first.returncode, 0, out1)
        self.assertNotEqual(second.returncode, 0, second.stdout)
        self.assertIn("another run", second.stdout)

    def test_two_takeovers_of_a_dead_lock_end_with_one_owner(self):
        repo, state = self.state_scene()
        ctx = state / "shop/product-context"; ctx.mkdir(parents=True, exist_ok=True)
        tmp = self.t / "tmp"; tmp.mkdir()
        key = subprocess.run(f"cd {ctx} && pwd -P | cksum | cut -d' ' -f1", shell=True, capture_output=True, text=True).stdout.strip()
        lock = tmp / f"dualtrack-{key}.lock"; lock.mkdir(); (lock / "pid").write_text("999999")  # a run that died
        a = subprocess.Popen(**self.run_sh(repo, TMPDIR=str(tmp), DUALTRACK_TEST_PAUSE_TAKEOVER="4"))
        time.sleep(1.5)  # a is paused between its check and its takeover
        b = subprocess.run(**self.run_sh(repo, TMPDIR=str(tmp)))
        a_out, _ = a.communicate(timeout=120)
        self.assertEqual(sum("stopped: another run" in o for o in (a_out, b.stdout)), 1, a_out + b.stdout)
        self.assertEqual(sorted([a.returncode == 0, b.returncode == 0]), [False, True], a_out + b.stdout)

    def test_first_run_agents_get_the_loops_guards(self):
        self.setup_agent()
        subprocess.run(["bash", str(KIT / "scripts/run.sh"), "profile.md"], cwd=self.t, capture_output=True, text=True,
                       env=dict(os.environ, CLAUDE=str(self.t / "claude"), ARGS_LOG=str(self.t / "args")))
        args = (self.t / "args").read_text()
        for guard in ("--setting-sources=", "--disable-slash-commands", "--disallowedTools", "Read(~/.ssh/**)", "Read(**/.env)"):
            self.assertIn(guard, args)


if __name__ == "__main__":
    unittest.main()
