#!/usr/bin/env python3
"""What has already been built: every open issue joined to the commits and merged pull requests behind it.

Before Dualtrack agents weigh in on an active repo they read this, not the issue text alone, so a fix that shipped weeks ago
and was never closed is not proposed again. Code does the join; a model only judges "done when" later, on the issues
this marks likely done.

  worklog.py [--repo DIR] [--days 90] [--out work.json]   build it; prints one count line
  worklog.py ... --issues FILE --prs FILE                 read gh's JSON from files instead (tests)

Per issue it keeps the number, title, labels, dates, checklist ticks, and the subjects of matching commits and pull
requests. Never the body or any author: the body is read only for ticks and the paths it names.
Status: likely done (a merged pull request closes it, or every checklist box is ticked), shipped, check (a merged pull
request refers to it without closing it: the model checks "done when"), in progress (only commits refer to it), not
started (none do). Commits on paths the issue names are kept as evidence but never set the status.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghrest  # noqa: E402
from loop_lib import NOTES_NEVER  # noqa: E402

PATH = re.compile(r"`?((?:[\w.-]+/)*[\w-]+\.(?:py|sh|md|js|ts|tsx|json|yml|yaml|toml|sql))(?::\d+)?`?")
STATUSES = ("likely done", "shipped, check", "in progress", "not started")
SCRUB = [re.compile(NOTES_NEVER[n], re.I) for n in ("a secret", "an email address", "a home path")]


def scrub(text):
    for p in SCRUB:
        text = p.sub("[removed]", text)
    return text


def opt(argv, name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


CLOSES = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+#(\d+)", re.I)


def pages(repo, path, keep, limit):
    """Up to `limit` rows from a REST list, a page at a time: GitHub's REST API only, since cloud sessions refuse GraphQL."""
    rows, page = [], 1
    while len(rows) < limit:
        got = ghrest.api(f"{path}&per_page=100&page={page}", cwd=repo)
        rows += [r for r in got if keep(r)]
        if len(got) < 100:
            break
        page += 1
    return rows[:limit]


def rest_issues(repo):
    """Open issues, in the shape `gh issue list --json` gave, from the REST list (which also holds pull requests)."""
    found = pages(repo, "repos/{owner}/{repo}/issues?state=open", lambda r: "pull_request" not in r, 500)
    return [{"number": i["number"], "title": i["title"], "labels": [{"name": l["name"]} for l in i.get("labels") or []],
             "createdAt": i["created_at"], "updatedAt": i["updated_at"], "body": i.get("body") or ""} for i in found]


def rest_prs(repo):
    """Merged pull requests. REST has no closingIssuesReferences, so a pull request closes what its text says it closes
    ("closes #7", "fixes #7", "resolves #7"), which is how GitHub reads it too; the text is read here and never kept."""
    found = pages(repo, "repos/{owner}/{repo}/pulls?state=closed&sort=updated&direction=desc", lambda r: r.get("merged_at"), 300)
    return [{"number": p["number"], "title": p["title"], "mergedAt": p["merged_at"],
             "closingIssuesReferences": [{"number": int(n)} for n in dict.fromkeys(CLOSES.findall(p.get("body") or ""))]} for p in found]


def commits(repo, days):
    """[(sha, date, subject, [paths])] from the last `days` days, newest first."""
    out = subprocess.run(["git", "log", f"--since={days} days ago", "--format=\x1e%h\t%ad\t%s", "--date=short",
                          "--name-only"], cwd=repo, capture_output=True, text=True, check=True).stdout
    found = []
    for block in out.split("\x1e")[1:]:
        head, *paths = block.strip("\n").split("\n")
        sha, date, subject = head.split("\t", 2)
        found.append((sha, date, subject, [p for p in paths if p]))
    return found


def ledger(issues, prs, log):
    rows = []
    for i in issues:
        n, body = i["number"], i.get("body") or ""
        ref = re.compile(rf"#{n}\b")
        named = {m.group(1) for m in PATH.finditer(body)}
        opened = i["createdAt"][:10]
        refs = [c for c in log if ref.search(c[2])]
        by_path = [c for c in log if c not in refs and c[1] >= opened
                   and any(p == q or p.endswith("/" + q) for p in c[3] for q in named)]
        closing = [p for p in prs if n in [r["number"] for r in p.get("closingIssuesReferences") or []]]
        mentioning = [p for p in prs if p not in closing and ref.search(p.get("title") or "")]
        ticked, boxes = len(re.findall(r"^\s*[-*] \[[xX]\]", body, re.M)), len(re.findall(r"^\s*[-*] \[[ xX]\]", body, re.M))
        # A path match alone is evidence, not status: README.md is touched by everything.
        if closing or (boxes and ticked == boxes):
            status = "likely done"
        elif mentioning:
            status = "shipped, check"
        elif refs:
            status = "in progress"
        else:
            status = "not started"
        dates = [c[1] for c in refs + by_path] + [(p.get("mergedAt") or "")[:10] for p in closing + mentioning]
        rows.append({
            "number": n, "title": scrub(i["title"]), "labels": [l["name"] for l in i.get("labels") or []],
            "opened": opened, "updated": i["updatedAt"][:10], "status": status,
            "checklist": f"{ticked}/{boxes}" if boxes else None,
            "last_code": max(dates) if dates else None,
            "commits": [f"{c[0]} {c[1]} {scrub(c[2])}" for c in refs[:5]],
            "commits_on_named_paths": [f"{c[0]} {c[1]} {scrub(c[2])}" for c in by_path[:3]],
            "pull_requests": [f"#{p['number']} {'closes' if p in closing else 'mentions'} {scrub(p['title'])}"
                              for p in (closing + mentioning)[:5]],
        })
    return rows


def main(argv):
    repo, days = opt(argv, "--repo", "."), int(opt(argv, "--days", "90"))
    origin = subprocess.run(["git", "-C", repo, "remote", "get-url", "origin"], capture_output=True, text=True)
    is_git = subprocess.run(["git", "-C", repo, "rev-parse", "--git-dir"], capture_output=True).returncode == 0
    if is_git and not opt(argv, "--issues") and "github.com" not in origin.stdout:
        print("work ledger: none yet, no GitHub repo")  # no issues or pull requests to read until there is one
        return 0
    try:
        issues = json.load(open(opt(argv, "--issues"))) if opt(argv, "--issues") else rest_issues(repo)
        prs = json.load(open(opt(argv, "--prs"))) if opt(argv, "--prs") else rest_prs(repo)
        log = commits(repo, days)
    except (subprocess.CalledProcessError, OSError, ValueError, SystemExit) as e:
        print(f"work ledger: unknown, could not read the repo's issues or history ({type(e).__name__})")
        return 1
    rows = ledger(issues, prs, log)
    out = opt(argv, "--out")
    if out:
        with open(out, "w") as f:
            json.dump({"days": days, "issues": rows}, f, indent=1)
    count = {s: sum(r["status"] == s for r in rows) for s in STATUSES}
    print(f"work ledger: {len(rows)} open issues, " + ", ".join(f"{count[s]} {s}" for s in STATUSES)
          + f" (commits from the last {days} days)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
