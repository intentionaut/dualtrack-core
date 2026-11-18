"""The merge gate: every check must hold, each failure names itself, and what it cannot read fails closed.

It runs through the real ghrest.py, with a fake gh underneath that answers the REST calls.
"""
import json
import os
import pathlib
import subprocess
import sys
import unittest

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
import merge_gate
try:
    import scratch
except ImportError:  # run as tests.test_x from the repo root
    from tests import scratch

SHA = "b" * 40
FAKE_GH = r'''#!/usr/bin/env python3
import json, os, sys
open(os.environ["LOG"], "a").write(" ".join(sys.argv[1:]) + "\n")
path = sys.argv[2]
if os.environ.get("BROKEN") == path.split("/")[-1].split("?")[0]: sys.exit(1)
if path.endswith("/merge"):
    print(json.dumps({"merged": True, "sha": "c" * 40}))
elif "/check-runs" in path and os.environ.get("FLIP") and open(os.environ["LOG"]).read().count("check-runs") == 1:
    print(json.dumps({"total_count": 1, "check_runs": [{"name": "t", "status": "queued", "conclusion": None}]}))
elif "/check-runs" in path:
    print(os.environ.get("RUNS") or json.dumps({"total_count": 1, "check_runs": [{"name": "test", "status": "completed", "conclusion": "success"}]}))
elif path.endswith("/status?per_page=100"):
    print(os.environ.get("STATUS") or json.dumps({"state": "pending", "statuses": []}))
elif "/git/ref/heads/" in path:
    print(json.dumps({"object": {"sha": os.environ.get("BASE_NOW", "a" * 40)}}))
elif "/pulls/" in path:
    print(json.dumps({"head": {"sha": os.environ.get("HEAD", "b" * 40)}, "base": {"ref": "main"}}))
'''
PROFILE = "**Auto-merge:** on\n\n**Surfaces:** cli\n\n**Required checks:** test\n\n**Protected path:** ^content/\n"


class Gate(unittest.TestCase):
    def setUp(self):
        self.t = pathlib.Path(scratch.mkdtemp())
        (self.t / "gh").write_text(FAKE_GH); (self.t / "gh").chmod(0o755)
        self.log = self.t / "log"
        self.run_dir = self.t / "run"; self.run_dir.mkdir()
        self.files = {"item.json": json.dumps({"visible": False}), "diff.txt": "M\tsrc/a.py\nA\ttests/test_a.py\n",
                      "numstat.txt": "3\t1\tsrc/a.py\n10\t0\ttests/test_a.py\n", "tests.result": "passed\n",
                      "diff.patch": "diff --git a/src/a.py b/src/a.py\n--- a/src/a.py\n+++ b/src/a.py\n@@ -1 +1 @@\n-x\n+y\n",
                      "base.sha": "a" * 40 + "\n", "first.result": "failed\n", "navigator.txt": "APPROVE\n", "ux-review.txt": "APPROVE\n", "code-review.txt": "APPROVE\n",
                      "intent.md": "a works: MET: test_a\n"}
        self.profile = PROFILE
        self.env = {"GH_BIN": str(self.t / "gh"), "LOG": str(self.log), "CI_WAIT": "0", "CI_POLL": "0"}

    def gate(self, **env):
        for name, text in self.files.items():
            (self.run_dir / name).write_text(text)
        (self.t / "profile.md").write_text(self.profile)
        r = subprocess.run([sys.executable, str(KIT / "scripts/merge_gate.py"), str(self.t / "profile.md"), str(self.run_dir), "7", SHA],
                           env={**os.environ, **self.env, **env}, capture_output=True, text=True)
        return r.returncode, r.stdout.strip()

    def merged(self):
        return self.log.exists() and "/merge" in self.log.read_text()

    def refused(self, why, **env):
        code, out = self.gate(**env)
        self.assertEqual(code, 4, out)
        self.assertIn(why, out)
        self.assertTrue(out.startswith("left for the owner: "))
        self.assertFalse(self.merged(), out)

    def test_all_checks_hold_so_it_squash_merges_the_reviewed_head(self):
        code, out = self.gate()
        self.assertEqual((code, out), (0, "merged " + "c" * 40))
        merge = [l for l in self.log.read_text().splitlines() if "/merge" in l][0]
        self.assertIn("-X PUT", merge); self.assertIn("merge_method=squash", merge); self.assertIn(f"sha={SHA}", merge)
        self.assertNotIn("graphql", self.log.read_text())

    def test_1_off_missing_or_placeholder(self):
        for line in ("**Auto-merge:** off\n", "", "**Auto-merge:** <off, or on to let the team merge>\n"):
            self.profile = PROFILE.replace("**Auto-merge:** on\n", line)
            self.refused("auto-merge is off")

    def test_2_protected_path(self):
        self.files["diff.txt"] = "M\tcontent/a.md\n"; self.files["numstat.txt"] = "1\t0\tcontent/a.md\n"
        self.refused("protected path content/a.md")

    def test_2_risky_files_are_named(self):
        for path, what in (("package.json", "manifest"), ("yarn.lock", "lockfile"), ("db/migrations/1.py", "migration"),
                           (".github/workflows/ci.yml", "CI"), ("Dockerfile", "deploy"), ("vercel.json", "deploy"),
                           (".env.local", "config"), ("app.config.ts", "config"), ("tsconfig.json", "config")):
            self.files["diff.txt"] = f"M\t{path}\n"; self.files["numstat.txt"] = f"1\t0\t{path}\n"
            self.refused(what)

    def test_2_ordinary_files_pass_the_path_check(self):
        for path in ("src/a.py", "tests/test_a.py", "README.md", "docs/configure.md", "src/settings_page.tsx"):
            self.assertIsNone(merge_gate.risky(path), path)

    def test_3_size(self):
        self.files["numstat.txt"] = "40\t11\tsrc/a.py\n"
        self.refused("51 lines in 2 files")
        self.files["numstat.txt"] = "1\t0\ta.py\n"; self.files["diff.txt"] = "M\ta.py\nM\tb.py\nM\tc.py\nM\td.py\n"
        self.refused("in 4 files")

    def test_3_bytes_symlinks_and_modes(self):
        self.files["diff.patch"] = "+" + "x" * 20001 + "\n"
        self.refused("bytes, over 20000")
        for line in ("new file mode 120000", "new mode 100755", "new file mode 100755"):
            self.setUp(); self.files["diff.patch"] = f"diff --git a/s b/s\n{line}\n"
            self.refused("file mode or a symlink")
        self.setUp(); self.files["diff.patch"] = "diff --git a/n.py b/n.py\nnew file mode 100644\n+x\n"
        self.assertEqual(self.gate()[0], 0)  # an ordinary new file passes
        self.setUp(); del self.files["diff.patch"]
        self.refused("unreadable: diff.patch")

    def test_4_a_line_left_to_check_after_merge_holds_the_merge(self):
        self.files["intent.md"] = "listed in the live sitemap: AFTER MERGE: open /sitemap.xml\n"
        self.refused("a Done when line is checked after merge")

    def test_4_every_reviewer_must_approve(self):
        for name, role in (("navigator.txt", "navigator"), ("ux-review.txt", "UX review"), ("code-review.txt", "Code Review")):
            self.setUp()
            self.files[name] = "CHANGES: findings\n"
            self.refused(f"{role} did not approve")

    def test_4_web_repo_needs_the_screenshot_check(self):
        self.profile = PROFILE.replace("cli", "web, docs")
        self.files["item.json"] = json.dumps({"visible": True})
        self.refused("unreadable: screens.txt")
        self.files["screens.txt"] = "none: no changed page to render\n"
        self.refused("screenshot check did not pass: none")
        self.files["screens.txt"] = "passed\n/run/screens/1.png\n"
        self.assertEqual(self.gate()[0], 0)

    def test_5_tests_must_pass(self):
        self.files["tests.result"] = "failed\n"
        self.refused("tests did not pass")

    def test_5_ci_must_be_green_on_the_exact_head(self):
        self.refused("not the reviewed", HEAD="d" * 40)
        failing = {"total_count": 1, "check_runs": [{"name": "t", "status": "completed", "conclusion": "failure"}]}
        self.refused("CI is not green", RUNS=json.dumps(failing))
        self.refused("CI is not green", RUNS=json.dumps({"total_count": 0, "check_runs": []}))  # no CI at all
        pending = {"total_count": 1, "check_runs": [{"name": "t", "status": "in_progress", "conclusion": None}]}
        self.refused("CI is not green", RUNS=json.dumps(pending))
        self.refused("CI is not green", STATUS=json.dumps({"state": "failure", "statuses": [{"context": "x", "state": "failure"}]}))
        self.refused("CI is not green", RUNS=json.dumps({"total_count": 101, "check_runs": [{"name": "t", "status": "completed", "conclusion": "success"}]}))

    def test_2_agent_instruction_files_are_risky(self):
        # A small change could rewrite the rules Code Review loads, then merge itself.
        for path in ("CLAUDE.md", "sub/AGENTS.md", "GEMINI.md", ".cursorrules", ".cursor/rules/a.mdc"):
            self.files["diff.txt"] = f"M\t{path}\n"; self.files["numstat.txt"] = f"1\t0\t{path}\n"
            self.refused("agent instructions")
        self.assertIsNone(merge_gate.risky("docs/claude-notes.md"))

    def test_2_tool_config_and_bare_github_are_risky(self):
        # These run code or change what installs on the next checkout, or are a symlink or submodule that stands in for .github/.
        for path in (".mcp.json", "sub/.mcp.json", ".husky/pre-commit", ".npmrc", ".yarnrc", ".pypirc", ".github"):
            self.assertIsNotNone(merge_gate.risky(path), path)
        for path in ("docs/npmrc.md", ".githubber", "src/husky.py"):
            self.assertIsNone(merge_gate.risky(path), path)

    def test_2_test_harness_deploy_scripts_owners_and_the_gate_are_risky(self):
        # A conftest can rewrite results, a deploy script ships, CODEOWNERS sets who must review, the gate is the lock itself.
        for path in ("conftest.py", "tests/conftest.py", "scripts/deploy.sh", "deploy-prod.sh", "bin/predeploy.py", "CODEOWNERS", "docs/CODEOWNERS",
                     "scripts/merge_gate.py", "scripts/loop_lib.py", "scripts/daily_loop.sh", "tests/test_merge_gate.py"):
            self.assertIsNotNone(merge_gate.risky(path), path)
        for path in ("docs/deployment.md", "src/conftest_notes.md", "scripts/merge_gate_notes.md", "src/owners.py", "scripts/status.py"):
            self.assertIsNone(merge_gate.risky(path), path)

    def test_2_agent_prompts_hooks_and_safety_files_are_never_auto_merged(self):
        # A small change here could loosen what the agents are told, what runs around them, or the files that pin them, then merge itself.
        for path, what in (("agents/engineer.md", "an agent prompt"), ("skills/dualtrack-setup/SKILL.md", "an agent prompt"), ("standards/ponytail.md", "an agent prompt"),
                           ("hooks/hooks.json", "a hook"), ("safety-files.json", "a safety file"), ("scripts/tamper.py", "a safety file"),
                           ("scripts/egress_proxy.py", "a safety file"), ("scripts/daily_loop.sh", "the merge gate"), (".github/workflows/test.yml", "CI"),
                           (".claude/settings.json", "config"), ("CLAUDE.md", "agent instructions"), (".mcp.json", "tool config")):
            self.files["diff.txt"] = f"M\t{path}\n"; self.files["numstat.txt"] = f"1\t0\t{path}\n"
            self.refused(what)
        self.files["diff.txt"] = "M\tsrc/a.py\n"; self.files["numstat.txt"] = "1\t0\tsrc/a.py\n"  # an ordinary change still merges
        self.assertEqual(self.gate()[0], 0); self.assertTrue(self.merged())

    def test_5_a_base_that_moved_after_review_holds_the_merge(self):
        self.refused("main moved", BASE_NOW="d" * 40)
        self.assertFalse(self.merged())

    def test_5_an_unrecorded_or_unreadable_base_holds_the_merge(self):
        del self.files["base.sha"]
        self.refused("unreadable: base.sha")
        self.files["base.sha"] = "a" * 40 + "\n"
        self.refused("unreadable", BROKEN="main")

    def test_5_the_tests_must_fail_with_the_code_put_back(self):
        for result in ("passed", "unprepared", "", "failed too"):
            self.files["first.result"] = result + "\n"
            self.refused("with the code put back")
        self.files["first.result"] = "not needed\n"  # docs or tests only: there is no code to put back
        self.assertEqual(self.gate()[0], 0)

    def test_5_a_missing_fail_first_result_holds_the_merge(self):
        del self.files["first.result"]
        self.refused("unreadable: first.result")

    def test_2_a_not_visible_flag_cannot_switch_off_review_of_a_visitor_path(self):
        # The PM sets visible; a false there skips design and UX review, so a diff a visitor would see is held whatever it says.
        for path in ("src/pages/index.astro", "README.md", "docs/guide.md"):
            self.files["diff.txt"] = f"M\t{path}\n"; self.files["numstat.txt"] = f"1\t0\t{path}\n"
            self.refused("a visitor would see")
        self.profile = PROFILE + "\n**Visitor paths:** ^site/\n"
        self.files["diff.txt"] = "M\tsite/a.txt\n"; self.files["numstat.txt"] = "1\t0\tsite/a.txt\n"
        self.refused("a visitor would see")
        self.files["item.json"] = json.dumps({"visible": True})  # reviewed as visible: the normal checks apply
        self.assertEqual(self.gate()[0], 0)

    def test_5_skipped_or_neutral_ci_is_not_green(self):
        for c in ("skipped", "neutral"):
            runs = {"total_count": 1, "check_runs": [{"name": "test", "status": "completed", "conclusion": c}]}
            self.refused("CI is not green", RUNS=json.dumps(runs))

    def test_5_waits_for_every_required_check(self):
        # The first suite to report is green, but a second required one has not registered yet.
        self.profile = PROFILE.replace("**Required checks:** test", "**Required checks:** test, lint")
        self.refused("CI is not green")
        both = {"total_count": 2, "check_runs": [{"name": n, "status": "completed", "conclusion": "success"} for n in ("test", "lint")]}
        self.assertEqual(self.gate(RUNS=json.dumps(both))[0], 0)

    def test_5_no_required_checks_line_fails_closed(self):
        for line in ("", "**Required checks:** <names of the CI checks that must pass>\n"):
            self.profile = PROFILE.replace("**Required checks:** test\n", line)
            self.refused("names no Required checks")

    def test_5_waits_for_ci_still_running_then_merges(self):
        self.refused("CI is not green", FLIP="1")  # no time to wait
        self.setUp()
        self.assertEqual(self.gate(FLIP="1", CI_WAIT="30")[0], 0)
        self.assertEqual(self.log.read_text().count("check-runs"), 2)

    def test_unreadable_data_fails_closed(self):
        for broken in ("7", "check-runs", "status"):
            self.refused("unreadable", BROKEN=broken)
        self.refused("unreadable: gh pr checks", RUNS="not json")
        self.refused("unreadable: gh pr checks", RUNS=json.dumps({"total_count": 1}))
        self.files["numstat.txt"] = "-\t-\tlogo.png\n"
        self.refused("unreadable: line count for logo.png")
        self.setUp(); del self.files["code-review.txt"]
        self.refused("unreadable: code-review.txt")
        self.setUp(); self.files["diff.txt"] = ""
        self.refused("unreadable: diff.txt is empty")

    def test_a_refused_merge_is_not_reported_as_merged(self):
        (self.t / "gh").write_text(FAKE_GH.replace('{"merged": True', '{"merged": False, "message": "Head branch was modified"'))
        code, out = self.gate()
        self.assertEqual(code, 4); self.assertIn("unreadable: gh pr merge", out)


if __name__ == "__main__":
    unittest.main()
