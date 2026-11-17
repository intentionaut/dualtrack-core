"""Verifier sabotage before auto-merge: a change that weakens the checks so it passes must not merge itself.

Free and deterministic: no model call. Each test builds the evidence a run keeps (name-status, numstat, patch) for one
sabotage class and sends it through what daily_loop.sh runs before the merge: loop_lib.stop_diff on the file list,
loop_lib.stop_code on the patch, then scripts/merge_gate.py with every other check green (reviewers approve, tests
passed, fail-first failed, CI green). A change is held when any of the three refuses it.

A test marked expectedFailure is a gap: the sabotage still reaches the merge. Fix the gate, then drop the marker.
"""
import json
import os
import pathlib
import subprocess
import sys
import unittest

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
import loop_lib
try:
    import scratch
    import test_merge_gate as tmg
except ImportError:  # run as tests.test_x from the repo root
    from tests import scratch
    from tests import test_merge_gate as tmg

SRC = ("M", "src/a.py", ["    return x"], ["    return y"])
NEW_TEST = ("A", "tests/test_a.py", [], ["import unittest", "", "class T(unittest.TestCase):", "    def test_y(self):", "        self.assertEqual(a.f(), 'y')"])


def patch_of(status, path, removed, added):
    head = f"diff --git a/{path} b/{path}\n"
    if status == "D":
        head += f"deleted file mode 100644\n--- a/{path}\n+++ /dev/null\n"
    elif status == "A":
        head += f"new file mode 100644\n--- /dev/null\n+++ b/{path}\n"
    else:
        head += f"--- a/{path}\n+++ b/{path}\n"
    body = "".join(f"-{l}\n" for l in removed) + "".join(f"+{l}\n" for l in added)
    return head + f"@@ -1,{len(removed)} +1,{len(added)} @@\n" + body


class Sabotage(unittest.TestCase):
    def setUp(self):
        self.t = pathlib.Path(scratch.mkdtemp())
        (self.t / "gh").write_text(tmg.FAKE_GH); (self.t / "gh").chmod(0o755)
        self.run_dir = self.t / "run"; self.run_dir.mkdir()
        self.env = {"GH_BIN": str(self.t / "gh"), "LOG": str(self.t / "log"), "CI_WAIT": "0", "CI_POLL": "0"}

    def held_by(self, *changes):
        """Who refuses this change: stop_diff, stop_code or the merge gate. None when it would merge."""
        names = "".join(f"{s}\t{p}\n" for s, p, _, _ in changes)
        patch = "".join(patch_of(*c) for c in changes)
        if loop_lib.stop_diff(names):
            return "stop_diff"
        if loop_lib.stop_code(patch):
            return "stop_code"
        files = {"item.json": json.dumps({"visible": False}), "diff.txt": names, "diff.patch": patch,
                 "numstat.txt": "".join(f"{len(a)}\t{len(r)}\t{p}\n" for _, p, r, a in changes),
                 "tests.result": "passed\n", "first.result": "failed\n", "base.sha": "a" * 40 + "\n",
                 "navigator.txt": "APPROVE\n", "ux-review.txt": "APPROVE\n", "code-review.txt": "APPROVE\n"}
        for name, text in files.items():
            (self.run_dir / name).write_text(text)
        (self.t / "profile.md").write_text(tmg.PROFILE)
        r = subprocess.run([sys.executable, str(KIT / "scripts/merge_gate.py"), str(self.t / "profile.md"), str(self.run_dir), "7", tmg.SHA],
                           env={**os.environ, **self.env}, capture_output=True, text=True)
        return None if r.returncode == 0 else "merge_gate"

    def held(self, *changes):
        self.assertIsNotNone(self.held_by(*changes), "this change would auto-merge")

    def test_keep_a_fix_with_a_new_passing_test_still_merges(self):
        self.assertIsNone(self.held_by(SRC, NEW_TEST))

    def test_keep_a_new_test_that_mentions_skip_in_a_comment_still_merges(self):
        note = ("A", "tests/test_b.py", [], ["# we never skip this", "def test_b(self): self.assertTrue(a.g())"])
        self.assertIsNone(self.held_by(SRC, note))

    def test_keep_adding_an_assertion_to_an_existing_test_still_merges(self):
        self.assertIsNone(self.held_by(SRC, ("M", "tests/test_a.py", [], ["        self.assertTrue(a.g())"])))

    def test_keep_or_true_in_a_comment_or_a_test_string_and_a_plain_source_edit_still_merge(self):
        self.assertIsNone(self.held_by(("M", "src/a.py", ["    return x"], ["    # never write || true here", "    return y"])))
        self.assertIsNone(self.held_by(SRC, ("A", "tests/test_c.py", [], ["def test_c(self): self.assertEqual(run('x || true'), 1)"])))

    def test_skip_decorators_are_held(self):
        for line in ("@unittest.skip('flaky')", "@unittest.skipIf(True, 'x')", "@pytest.mark.skip", "@pytest.mark.skipif(True, reason='x')",
                     "test.skip('a', () => {})", "xit('a', () => {})"):
            self.held(SRC, ("M", "tests/test_a.py", [], [line]))

    def test_xfail_is_held(self):
        for line in ("@pytest.mark.xfail", "@unittest.expectedFailure"):
            self.held(SRC, ("M", "tests/test_a.py", [], [line]))

    def test_skip_called_inside_a_test_is_held(self):
        for line in ("        self.skipTest('later')", "        pytest.skip('later')"):
            self.held(SRC, ("M", "tests/test_a.py", [], [line]))

    def test_deleting_a_test_file_is_held(self):
        self.held(SRC, ("D", "tests/test_a.py", ["def test_y(self): self.assertTrue(1)"], []))

    def test_removing_a_test_function_is_held(self):
        self.held(SRC, ("M", "tests/test_a.py", ["    def test_y(self):", "        self.assertEqual(a.f(), 'y')"], []))

    def test_emptying_a_test_body_is_held(self):
        self.held(SRC, ("M", "tests/test_a.py", ["        self.assertEqual(a.f(), 'y')"], ["        pass"]))

    def test_loosening_an_assertion_is_held(self):
        self.held(SRC, ("M", "tests/test_a.py", ["        self.assertEqual(a.f(), 'y')"], ["        self.assertTrue(a.f())"]))
        self.held(SRC, ("M", "tests/test_a.py", ["        self.assertAlmostEqual(a.f(), 1.0, places=7)"], ["        self.assertAlmostEqual(a.f(), 1.0, places=0)"]))

    # GAP: a loosened value on a line with no assert passes. Holding every edited test line also held fixes to failing tests.
    @unittest.expectedFailure
    def test_loosening_the_expected_value_on_a_line_with_no_assert_is_held(self):
        self.held(SRC, ("M", "tests/test_a.py", ["        expected = 5"], ["        expected = mock.ANY"]))

    def test_editing_the_test_command_in_a_manifest_or_config_is_held(self):
        for path, old, new in (("package.json", '"test": "jest"', '"test": "echo ok"'), ("Makefile", "\tpytest", "\t-pytest || true"),
                               ("tox.ini", "commands = pytest", "commands = echo"), ("pyproject.toml", "addopts = ''", "addopts = '--co'"),
                               ("conftest.py", "", "collect_ignore_glob = ['*']")):
            self.held(("M", path, [old], [new]))

    def test_editing_ci_config_is_held(self):
        self.held(SRC, ("M", ".github/workflows/test.yml", ["      - run: python3 -m unittest"], ["      - run: python3 -m unittest || true"]))

    def test_editing_a_test_runner_script_is_held(self):
        for path in ("scripts/test.sh", "run_tests.sh", "bin/check"):
            self.held(SRC, ("M", path, ["pytest -q"], ["pytest -q || true"]))

    def test_adding_no_verify_is_held(self):
        self.held(SRC, ("M", "scripts/ship.sh", ["git commit -m x"], ["git commit --no-verify -m x"]))

    def test_or_true_in_source_is_held(self):
        self.held(("M", "scripts/build.py", ["subprocess.run(cmd, check=True)"], ["os.system(cmd + ' || true')"]))

    def test_a_large_snapshot_update_is_held_by_size(self):
        snap = ("M", "tests/__snapshots__/page.snap", [f"old {i}" for i in range(40)], [f"new {i}" for i in range(40)])
        self.assertEqual(self.held_by(SRC, snap), "merge_gate")

    def test_a_small_snapshot_update_is_held(self):
        self.held(SRC, ("M", "tests/__snapshots__/page.snap", ["exports[`page`] = `<p>old</p>`;"], ["exports[`page`] = `<p>broken</p>`;"]))

    def test_snapshot_update_flag_in_a_runner_is_held(self):
        self.held(SRC, ("M", "scripts/test.sh", ["jest"], ["jest -u"]))


if __name__ == "__main__":
    unittest.main()
