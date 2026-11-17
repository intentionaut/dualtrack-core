"""A broken baseline: reading the failing tests, CI's word on the base commit, and the issue that tells the owner."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
import loop_lib
try:
    import scratch
except ImportError:  # run as tests.test_x from the repo root
    from tests import scratch

UNITTEST = """..F.E
======================================================================
FAIL: test_a (tests.test_x.X.test_a)
----------------------------------------------------------------------
Traceback (most recent call last):
AssertionError: 1 != 2

======================================================================
ERROR: test_b (tests.test_x.X.test_b)
----------------------------------------------------------------------
KeyError: 'k'

======================================================================
FAIL: test_a (tests.test_x.X.test_a)
----------------------------------------------------------------------
Ran 5 tests in 0.1s

FAILED (failures=2, errors=1)
"""
PYTEST = """=================== short test summary info ====================
FAILED tests/test_a.py::test_one - assert 1 == 2
FAILED tests/test_a.py::Klass::test_two[x-1] - KeyError
ERROR tests/test_b.py - ImportError: no module named q
=========== 2 failed, 1 error in 0.20s ===========
"""


class Failing(unittest.TestCase):
    def test_unittest_ids(self):
        self.assertEqual(loop_lib.failing_tests(UNITTEST), ["test_a (tests.test_x.X.test_a)", "test_b (tests.test_x.X.test_b)"])

    def test_pytest_ids(self):
        self.assertEqual(loop_lib.failing_tests(PYTEST), ["tests/test_a.py::Klass::test_two[x-1]", "tests/test_a.py::test_one", "tests/test_b.py"])

    def test_no_ids_means_none_and_the_tail_is_twenty_lines_not_one(self):
        out = "".join(f"row {n}\n" for n in range(1, 41))
        self.assertEqual(loop_lib.failing_tests(out), [])
        tail = loop_lib.output_tail(out)
        self.assertEqual(len(tail), 20); self.assertEqual((tail[0], tail[-1]), ("row 21", "row 40"))

    def test_same_or_fewer_failures_are_no_new_failures_and_a_new_one_is_not(self):
        base = "FAIL: a (m.A.a)\nFAIL: b (m.A.b)\n"
        self.assertTrue(loop_lib.no_new_failures(base, base))
        self.assertTrue(loop_lib.no_new_failures(base, "FAIL: a (m.A.a)\n"))
        self.assertFalse(loop_lib.no_new_failures(base, base + "FAIL: c (m.A.c)\n"))
        self.assertFalse(loop_lib.no_new_failures(base, "FAIL: c (m.A.c)\n"))

    def test_unreadable_names_prove_nothing(self):
        self.assertFalse(loop_lib.no_new_failures("boom\n", "boom\n"))
        self.assertFalse(loop_lib.no_new_failures("FAIL: a (m.A.a)\n", "boom\n"))
        self.assertFalse(loop_lib.no_new_failures("boom\n", "FAIL: a (m.A.a)\n"))


def checks(*runs, statuses=(), state="pending"):
    return {"total": len(runs), "runs": [{"name": n, "status": s, "conclusion": c} for n, s, c in runs],
            "state": state, "statuses": [{"context": n, "state": s} for n, s in statuses]}


class CiState(unittest.TestCase):
    def test_green_red_and_everything_else_is_unknown(self):
        ok, bad, wait = ("t", "completed", "success"), ("t", "completed", "failure"), ("t", "in_progress", None)
        self.assertEqual(loop_lib.ci_state(checks(ok), {"t"}), "green")
        self.assertEqual(loop_lib.ci_state(checks(bad), {"t"}), "red")
        self.assertEqual(loop_lib.ci_state(checks(wait), {"t"}), "unknown")
        self.assertEqual(loop_lib.ci_state(checks(ok), set()), "unknown")  # no Required checks: nothing to judge by
        self.assertEqual(loop_lib.ci_state(checks(), {"t"}), "unknown")
        self.assertEqual(loop_lib.ci_state(checks(("t", "completed", "skipped")), {"t"}), "unknown")
        self.assertEqual(loop_lib.ci_state(checks(("other", "completed", "failure"), ok), {"t"}), "unknown")  # another check failed: not green, and not the required one
        self.assertEqual(loop_lib.ci_state(None, {"t"}), "unknown")

    def test_a_failed_status_on_a_required_name_is_red(self):
        self.assertEqual(loop_lib.ci_state(checks(statuses=[("t", "failure")], state="failure"), {"t"}), "red")


class Issue(unittest.TestCase):
    def test_the_fingerprint_is_stable_for_the_same_failures_and_differs_for_others(self):
        a = loop_lib.baseline_issue("FAIL: a (m.A.a)\nFAIL: b (m.A.b)\n", "1" * 40, "unknown")
        b = loop_lib.baseline_issue("FAIL: b (m.A.b)\nFAIL: a (m.A.a)\nRan 2 tests in 9.9s\n", "2" * 40, "red")
        c = loop_lib.baseline_issue("FAIL: c (m.A.c)\n", "1" * 40, "unknown")
        self.assertEqual(a["fingerprint"], b["fingerprint"]); self.assertNotEqual(a["fingerprint"], c["fingerprint"])
        self.assertIn(f"<!-- dualtrack-baseline:{a['fingerprint']} -->", a["body"])
        self.assertIn("- a (m.A.a)", a["body"])

    def test_without_names_the_fingerprint_ignores_numbers_such_as_timings(self):
        one = loop_lib.baseline_issue("setup broke\nRan in 1.2s\n", "1" * 40, "unknown")
        two = loop_lib.baseline_issue("setup broke\nRan in 9.8s\n", "1" * 40, "unknown")
        self.assertEqual(one["fingerprint"], two["fingerprint"])

    def test_find_matches_the_fingerprint_in_an_open_issue_body(self):
        issues = [{"number": 3, "body": "no"}, {"number": 9, "body": "x\n<!-- dualtrack-baseline:abc123abc123 -->"}]
        self.assertEqual(loop_lib.find_issue(issues, "abc123abc123"), 9)
        self.assertIsNone(loop_lib.find_issue(issues, "ffffffffffff"))


class Item(unittest.TestCase):
    def test_get_main_green_is_a_full_item_naming_the_failing_tests(self):
        item = loop_lib.green_item("FAIL: a (m.A.a)\nFAIL: b (m.A.b)\n")
        self.assertEqual(item["title"], "Get main green")
        for f in loop_lib.ITEM_FIELDS:
            self.assertTrue(item.get(f), f)
        self.assertIn("a (m.A.a)", item["what"]); self.assertIs(item["visible"], False)
        self.assertIn(item["move"], loop_lib.MOVES)
        self.assertEqual(loop_lib.stop_reason(item["title"]), None)  # not on the stop list


GH = r'''#!/usr/bin/env python3
import json, os, sys
open(os.environ["LOG"], "a").write(" ".join(sys.argv[1:]) + "\n")
path = sys.argv[2]
if "/issues?" in path: print(json.dumps([{"number": 5, "body": "<!-- dualtrack-baseline:abc123abc123 -->"},
                                         {"number": 6, "body": "a pull request", "pull_request": {"url": "u"}}]))
elif path.endswith("/issues"): print(json.dumps({"number": 8, "html_url": "https://github.com/o/r/issues/8"}))
else: print("{}")
'''


class GhRestIssues(unittest.TestCase):
    def setUp(self):
        self.t = pathlib.Path(scratch.mkdtemp())
        (self.t / "gh").write_text(GH); (self.t / "gh").chmod(0o755)
        self.env = dict(os.environ, GH_BIN=str(self.t / "gh"), LOG=str(self.t / "log"))

    def rest(self, *args):
        r = subprocess.run([sys.executable, str(KIT / "scripts/ghrest.py"), *args], env=self.env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_issue_list_create_and_comment_are_rest_calls(self):
        listed = json.loads(self.rest("issue", "list", "--state", "open", "--label", "dualtrack", "--json", "number,body"))
        self.assertEqual(listed, [{"number": 5, "body": "<!-- dualtrack-baseline:abc123abc123 -->"}])  # pull requests are not issues
        body = self.t / "body.md"; body.write_text("hello")
        self.assertEqual(self.rest("issue", "create", "--title", "T", "--body-file", str(body), "--label", "dualtrack"), "https://github.com/o/r/issues/8")
        self.rest("issue", "comment", "5", "--body-file", str(body))
        log = (self.t / "log").read_text()
        self.assertIn("labels=dualtrack", log); self.assertIn("repos/{owner}/{repo}/issues/5/comments", log)
        self.assertNotIn("graphql", log)


class Gate(unittest.TestCase):
    def test_no_new_failures_never_auto_merges(self):
        import merge_gate
        with tempfile.TemporaryDirectory() as d:
            run = pathlib.Path(d)
            for name, text in {"diff.txt": "M\tsrc/a.py\n", "numstat.txt": "1\t1\tsrc/a.py\n", "diff.patch": "diff --git a/src/a.py b/src/a.py\n",
                               "navigator.txt": "APPROVE\n", "ux-review.txt": "APPROVE\n", "code-review.txt": "APPROVE\n",
                               "item.json": "{}", "tests.result": "no new failures\n"}.items():
                (run / name).write_text(text)
            profile = "**Auto-merge:** on\n\n**Surfaces:** cli\n\n**Required checks:** test\n"
            with self.assertRaises(merge_gate.Fail) as e:
                merge_gate.gate(profile, str(run), "7", "b" * 40)
            self.assertIn("no new failures", str(e.exception))


if __name__ == "__main__":
    unittest.main()
