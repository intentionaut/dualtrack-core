"""ghrest.py speaks REST only, and gives the loop the shape gh pr list gives it."""
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
FAKE = r'''#!/usr/bin/env python3
import json, os, sys
open(os.environ["LOG"], "a").write(" ".join(sys.argv[1:]) + "\n")
path = sys.argv[2]
if "graphql" in path: sys.exit(1)
if path.startswith("repos/{owner}/{repo}/issues?") and "labels=team-daily" in path:
    print(json.dumps([
        {"number": 3, "title": "open one", "state": "open", "closed_at": None, "html_url": "https://github.com/o/r/pull/3", "pull_request": {"merged_at": None}},
        {"number": 2, "title": "merged", "state": "closed", "closed_at": "2026-11-02T10:00:00Z", "html_url": "u2", "pull_request": {"merged_at": "2026-11-02T10:00:00Z"}},
        {"number": 9, "title": "an issue, not a pull request", "state": "open", "closed_at": None, "html_url": "u9"}]))
elif path == "repos/{owner}/{repo}/pulls/3":
    print(json.dumps({"head": {"ref": "team/x"}}))
elif path.startswith("repos/{owner}/{repo}/pulls?"):
    print(json.dumps([
        {"number": 3, "title": "open one", "state": "open", "merged_at": None, "closed_at": None, "labels": [{"name": "team-daily"}], "head": {"ref": "team/x"}, "html_url": "https://github.com/o/r/pull/3"},
        {"number": 2, "title": "merged", "state": "closed", "merged_at": "2026-11-02T10:00:00Z", "closed_at": "2026-11-02T10:00:00Z", "labels": [{"name": "team-daily"}]},
        {"number": 1, "title": "someone else's", "state": "closed", "merged_at": None, "closed_at": "2026-11-01T10:00:00Z", "labels": []}]))
elif path.endswith("/comments"):
    print(json.dumps([{"body": "not now: wrong page", "user": {"login": "sam", "type": "User"}, "author_association": "MEMBER"}]))
elif path == "repos/{owner}/{repo}/pulls/4" and "-H" in sys.argv:
    print("diff --git a/x b/x")
elif path == "repos/{owner}/{repo}/pulls/4":
    print(json.dumps({"number": 4, "title": "t", "body": None, "state": "open", "draft": False, "merged_at": None,
                      "user": {"login": "u"}, "head": {"sha": "a"}, "base": {"ref": "main"}, "html_url": "h"}))
elif "/pulls/4/files" in path:
    print(json.dumps([{"filename": "x.py"}]))
elif "/reviews" in path or "/4/comments?" in path:
    print(json.dumps([{"user": {"login": "u", "type": "User"}, "state": "COMMENTED", "body": "b", "author_association": "OWNER",
                       "submitted_at": "2026-11-07T09:00:00Z", "created_at": "2026-11-07T09:00:00Z", "path": "x.py"}]))
elif path == "repos/{owner}/{repo}/pulls":
    print(json.dumps({"number": 4, "html_url": "https://github.com/o/r/pull/4"}))
else:
    print(json.dumps({"html_url": "https://github.com/o/r", "visibility": "private"}))
'''


class GhRest(unittest.TestCase):
    def setUp(self):
        self.t = pathlib.Path(scratch.mkdtemp())
        (self.t / "gh").write_text(FAKE); (self.t / "gh").chmod(0o755)
        self.log = self.t / "log"
        self.env = dict(os.environ, GH_BIN=str(self.t / "gh"), LOG=str(self.log))

    def run_rest(self, *args):
        r = subprocess.run([sys.executable, str(KIT / "scripts/ghrest.py"), *args], env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_pr_list_keeps_only_the_label_and_maps_states(self):
        rows = json.loads(self.run_rest("pr", "list", "--state", "all", "--label", "team-daily", "--limit", "50", "--json", "x"))
        self.assertEqual([(r["number"], r["state"]) for r in rows], [(3, "OPEN"), (2, "MERGED")])
        self.assertEqual(rows[1]["comments"], [{"body": "not now: wrong page", "author": {"login": "sam", "type": "User"},
                                                "authorAssociation": "MEMBER"}])
        self.assertEqual(rows[0]["comments"], [])

    def test_pr_create_opens_a_ready_pull_request_and_labels_it(self):
        body = self.t / "body.md"; body.write_text("trail")
        url = self.run_rest("pr", "create", "--base", "main", "--head", "team/y", "--title", "T",
                            "--body-file", str(body), "--label", "team-daily")
        self.assertEqual(url, "https://github.com/o/r/pull/4")
        calls = self.log.read_text().splitlines()
        self.assertIn("draft=false", calls[1])
        self.assertIn("issues/4/labels", calls[2])

    def test_pr_create_for_a_branch_that_already_has_an_open_pull_request_labels_it_and_opens_no_second(self):
        body = self.t / "body.md"; body.write_text("trail")  # the fake's open pull request 3 is on team/x
        url = self.run_rest("pr", "create", "--base", "main", "--head", "team/x", "--title", "T",
                            "--body-file", str(body), "--label", "team-daily")
        self.assertEqual(url, "https://github.com/o/r/pull/3")
        calls = self.log.read_text().splitlines()
        self.assertFalse([c for c in calls if "draft=false" in c], calls)
        self.assertIn("issues/3/labels", calls[-1])

    def test_review_reads_are_rest_gets_and_write_nothing(self):
        for what in ("info", "diff", "files", "comments", "reviews"):
            self.run_rest("pr", what, "4")
        calls = self.log.read_text().splitlines()
        self.assertTrue(calls and all(l.startswith("api repos/") for l in calls))
        self.assertFalse(any(" -X " in f" {l} " or " -f " in f" {l} " or " -F " in f" {l} " for l in calls), calls)
        self.assertNotIn("graphql", self.log.read_text())
        bad = subprocess.run([sys.executable, str(KIT / "scripts/ghrest.py"), "pr", "comment", "4"], env=self.env, capture_output=True)
        self.assertNotEqual(bad.returncode, 0)

    def test_comments_and_reviews_say_who_and_when_so_the_loop_can_trust_and_date_them(self):
        for what in ("comments", "reviews"):
            row = json.loads(self.run_rest("pr", what, "4"))[-1]
            self.assertEqual(row["author"], {"login": "u", "type": "User"})
            self.assertEqual(row["authorAssociation"], "OWNER")
            self.assertEqual(row["createdAt"], "2026-11-07T09:00:00Z")

    def test_list_asks_github_for_the_label_so_a_busy_repo_cannot_hide_the_open_change(self):
        rows = json.loads(self.run_rest("pr", "list", "--state", "all", "--label", "team-daily", "--limit", "50", "--json", "x"))
        self.assertEqual([(r["number"], r["state"]) for r in rows], [(3, "OPEN"), (2, "MERGED")])
        self.assertNotIn("pulls?state=all", self.log.read_text())

    def test_list_names_each_branch_and_link(self):
        rows = json.loads(self.run_rest("pr", "list", "--state", "all", "--label", "team-daily", "--limit", "5", "--json", "x"))
        self.assertEqual((rows[0]["headRefName"], rows[0]["url"]), ("team/x", "https://github.com/o/r/pull/3"))

    def test_repo_view_gives_the_visibility_the_loop_asks_for_as_gh_prints_it(self):
        # daily_loop.sh treats anything but PRIVATE or INTERNAL as public, so a URL here made every repo public
        self.assertEqual(self.run_rest("repo", "view", "--json", "visibility", "-q", ".visibility"), "PRIVATE")
        self.assertEqual(self.run_rest("repo", "view", "--json", "url", "-q", ".url"), "https://github.com/o/r")

    def test_never_uses_graphql(self):
        self.run_rest("repo", "view", "--json", "url", "-q", ".url")
        self.run_rest("pr", "list", "--state", "all", "--label", "team-daily", "--limit", "5", "--json", "x")
        self.assertNotIn("graphql", self.log.read_text())
        self.assertTrue(all(l.startswith("api ") for l in self.log.read_text().splitlines()))

    def test_a_github_that_never_answers_ends_the_call_instead_of_hanging(self):
        import time
        (self.t / "gh").write_text("#!/bin/sh\nsleep 60\n")
        t0 = time.time()
        r = subprocess.run([sys.executable, str(KIT / "scripts/ghrest.py"), "repo", "view", "--json", "url", "-q", ".url"],
                           env=dict(self.env, GHREST_TIMEOUT="2"), capture_output=True, text=True)
        self.assertLess(time.time() - t0, 20); self.assertNotEqual(r.returncode, 0)
        self.assertIn("GitHub did not answer", r.stderr)
        # the same call, to a gh that answers, is not cut off
        (self.t / "gh").write_text(FAKE)
        self.assertEqual(self.run_rest("repo", "view", "--json", "url", "-q", ".url"), "https://github.com/o/r")


if __name__ == "__main__":
    unittest.main()
