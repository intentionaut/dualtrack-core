"""worklog.py: open issues joined to the work behind them, so the team never proposes what already shipped."""
import json
import os
import pathlib
import subprocess
import sys
import unittest
try:
    import scratch
except ImportError:  # run as tests.test_x from the repo root
    from tests import scratch

KIT = pathlib.Path(__file__).resolve().parent.parent


def issue(n, title, body=""):
    return {"number": n, "title": title, "labels": [{"name": "bug"}], "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-02T00:00:00Z", "body": body}


# A gh that speaks REST only, as a cloud session's does: anything else (GraphQL, `issue list`, `pr list`) fails.
FAKE_GH = r'''#!/usr/bin/env python3
import json, os, re, sys
open(os.environ["LOG"], "a").write(" ".join(sys.argv[1:]) + "\n")
if sys.argv[1] != "api" or "graphql" in " ".join(sys.argv):
    sys.stderr.write("GraphQL is refused here\n"); sys.exit(1)
path = sys.argv[2]
page = int(re.search(r"&page=(\d+)", path)[1])
if path.startswith("repos/{owner}/{repo}/issues?state=open"):
    rows = [{"number": n, "title": f"issue {n}", "labels": [{"name": "bug"}], "created_at": "2026-01-01T00:00:00Z",
             "updated_at": "2026-01-02T00:00:00Z", "body": "x"} for n in range(1, 101)] if page == 1 else [
            {"number": 101, "title": "last", "labels": [], "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-02T00:00:00Z", "body": None},
            {"number": 102, "title": "a pull request", "pull_request": {}, "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-02T00:00:00Z"}]
    print(json.dumps(rows))
elif path.startswith("repos/{owner}/{repo}/pulls?state=closed"):
    print(json.dumps([{"number": 20, "title": "Fix it", "merged_at": "2026-02-01T00:00:00Z", "body": "Closes #1 and fixes #2. Only mentions #3."},
                      {"number": 21, "title": "Abandoned", "merged_at": None, "body": "closes #4"}]))
else:
    sys.exit(2)
'''


class Worklog(unittest.TestCase):
    def setUp(self):
        self.t = pathlib.Path(scratch.mkdtemp())
        git = lambda *a: subprocess.run(["git", "-C", str(self.t), *a], check=True, capture_output=True)
        git("init", "-q")
        git("config", "user.email", "t@example.com")
        git("config", "user.name", "t")
        for path, msg in (("a.py", "Start the parser (Refs #3)"), ("lib/named.py", "Tidy, no issue number"),
                          ("b.py", "Touch #10 only")):
            (self.t / path).parent.mkdir(exist_ok=True)
            (self.t / path).write_text(msg)
            git("add", ".")
            git("commit", "-qm", msg)
        issues = [
            issue(1, "Closed by a merged pull request"),
            issue(2, "Shipped under Refs, never closed"),
            issue(3, "Only a commit so far"),
            issue(4, "Every box ticked", "- [x] one\n- [x] two\n"),
            issue(5, "Names a path someone touched", "The bug is in `named.py:12`. Mail ada@example.com"),
            issue(6, "Nothing at all"),
        ]
        prs = [{"number": 20, "title": "Fix it", "mergedAt": "2026-02-01T00:00:00Z",
                "closingIssuesReferences": [{"number": 1}]},
               {"number": 21, "title": "Most of it (Refs #2)", "mergedAt": "2026-02-02T00:00:00Z",
                "closingIssuesReferences": []}]
        (self.t / "issues.json").write_text(json.dumps(issues))
        (self.t / "prs.json").write_text(json.dumps(prs))

    def run_it(self):
        r = subprocess.run([sys.executable, str(KIT / "scripts/worklog.py"), "--repo", str(self.t), "--days", "3650",
                            "--issues", str(self.t / "issues.json"), "--prs", str(self.t / "prs.json"),
                            "--out", str(self.t / "work.json")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout, {i["number"]: i for i in json.loads((self.t / "work.json").read_text())["issues"]}

    def test_each_issue_gets_the_status_its_work_shows(self):
        out, work = self.run_it()
        self.assertEqual({n: w["status"] for n, w in work.items()},
                         {1: "likely done", 2: "shipped, check", 3: "in progress", 4: "likely done",
                          5: "not started", 6: "not started"})
        self.assertIn("6 open issues, 2 likely done, 1 shipped, check, 1 in progress, 2 not started", out)

    def test_the_evidence_is_named(self):
        _, work = self.run_it()
        self.assertEqual(work[2]["pull_requests"], ["#21 mentions Most of it (Refs #2)"])
        self.assertTrue(work[3]["commits"][0].endswith("Start the parser (Refs #3)"))
        self.assertEqual(work[4]["checklist"], "2/2")

    def test_a_named_path_is_evidence_but_never_status(self):
        """README.md is touched by everything, so a path match alone must not read as work on the issue."""
        _, work = self.run_it()
        self.assertEqual(len(work[5]["commits_on_named_paths"]), 1)
        self.assertEqual(work[5]["status"], "not started")

    def test_issue_one_is_not_issue_ten(self):
        _, work = self.run_it()
        self.assertEqual(work[1]["commits"], [])

    def test_no_body_and_no_author_leave_the_machine(self):
        self.run_it()
        text = (self.t / "work.json").read_text()
        self.assertNotIn("ada@example.com", text)
        self.assertNotIn("The bug is in", text)
        self.assertNotIn("t@example.com", text)

    def test_an_unreadable_repo_says_unknown_and_never_a_count(self):
        r = subprocess.run([sys.executable, str(KIT / "scripts/worklog.py"), "--repo", str(self.t / "missing")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("work ledger: unknown", r.stdout)


    def test_a_repo_with_no_github_remote_says_none_yet_and_calls_no_github(self):
        r = subprocess.run([sys.executable, str(KIT / "scripts/worklog.py"), "--repo", str(self.t)], capture_output=True,
                           text=True, env=dict(__import__("os").environ, PATH="/usr/bin:/bin"))
        self.assertEqual((r.returncode, r.stdout.strip()), (0, "work ledger: none yet, no GitHub repo"))

    def test_it_reads_issues_and_merged_pull_requests_over_rest_only(self):
        gh = self.t / "gh"; gh.write_text(FAKE_GH); gh.chmod(0o755)
        subprocess.run(["git", "-C", str(self.t), "remote", "add", "origin", "https://github.com/o/r.git"], check=True)
        log = self.t / "gh.log"
        r = subprocess.run([sys.executable, str(KIT / "scripts/worklog.py"), "--repo", str(self.t), "--days", "3650",
                            "--out", str(self.t / "rest.json")], capture_output=True, text=True,
                           env=dict(os.environ, GH_BIN=str(gh), LOG=str(log)))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        work = {i["number"]: i for i in json.loads((self.t / "rest.json").read_text())["issues"]}
        self.assertEqual(len(work), 101)  # a second page was read, and the pull request among the issues was left out
        self.assertEqual(work[1]["status"], "likely done"); self.assertEqual(work[2]["status"], "likely done")
        self.assertNotEqual(work[3]["status"], "likely done"); self.assertNotEqual(work[4]["status"], "likely done")
        self.assertTrue(all(l.startswith("api ") for l in log.read_text().splitlines()), log.read_text())

    def test_a_gh_that_refuses_gives_the_unknown_line_not_a_crash(self):
        gh = self.t / "gh"; gh.write_text("#!/bin/sh\nexit 1\n"); gh.chmod(0o755)
        subprocess.run(["git", "-C", str(self.t), "remote", "add", "origin", "https://github.com/o/r.git"], check=True)
        r = subprocess.run([sys.executable, str(KIT / "scripts/worklog.py"), "--repo", str(self.t)], capture_output=True, text=True,
                           env=dict(os.environ, GH_BIN=str(gh)))
        self.assertEqual(r.returncode, 1); self.assertIn("work ledger: unknown", r.stdout)


if __name__ == "__main__":
    unittest.main()
