#!/usr/bin/env python3
"""The gh commands the loop uses, over the REST API only.

Claude Code cloud sessions refuse GitHub GraphQL, which `gh pr list`, `gh pr create`
and `gh repo view` use. This speaks REST through `gh api`, so the same loop runs
locally and in a cloud routine. Output matches what the loop reads from gh.

Usage, as the loop calls it (GH=scripts/ghrest.py):
  ghrest.py pr list --state all --label L --limit N --json ...
  ghrest.py repo view --json url -q .url   (or --json visibility: PRIVATE, PUBLIC or INTERNAL)
  ghrest.py label create L --force
  ghrest.py pr create --base B --head H --title T --body-file F --label L   (ready, not a draft)
  ghrest.py pr view N --json headRefOid -q .headRefOid
  ghrest.py pr checks SHA                   check runs and statuses on that commit, as JSON
  ghrest.py pr base N                       the commit the pull request's base branch is at now
  ghrest.py pr merge N --squash --match-head-commit SHA   print the merged commit
  ghrest.py issue list --state open --label L --json number,body   issues only, never pull requests, as JSON
  ghrest.py issue create --title T --body-file F --label L         print the new issue's URL
  ghrest.py issue comment N --body-file F

Read-only, for Code Review (each is one REST GET; none can write):
  ghrest.py pr info N        title, body, state, draft, author, head and base, as JSON
  ghrest.py pr diff N        the unified diff
  ghrest.py pr files N       changed file paths, one a line
  ghrest.py pr comments N    issue and review comments, with author, association and time, as JSON
  ghrest.py pr reviews N     reviews, the same way
"""
import json
import os
import subprocess
import sys
import urllib.parse

GH = os.environ.get("GH_BIN", "gh")
TIMEOUT = int(os.environ.get("GHREST_TIMEOUT") or 60)  # seconds a call may take; a dead network ends the run instead of hanging it


def api(path, *fields, method=None, cwd=None):
    cmd = [GH, "api", path] + (["-X", method] if method else []) + list(fields)
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=TIMEOUT, cwd=cwd,
                             env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    except subprocess.TimeoutExpired:
        raise SystemExit(f"ghrest: GitHub did not answer {path} in time (GHREST_TIMEOUT)")
    if out.returncode:
        sys.stderr.write(out.stderr)
        raise SystemExit(out.returncode)
    return json.loads(out.stdout or "null")


def opt(args, name, default=None):
    return args[args.index(name) + 1] if name in args else default


def pr_list(args):
    label, limit = opt(args, "--label"), int(opt(args, "--limit", "30"))
    rows = []
    if label:
        # GitHub filters by label, so Dualtrack's changes are found however many other pull requests a repo has.
        found = api(f"repos/{{owner}}/{{repo}}/issues?state=all&labels={urllib.parse.quote(label)}&per_page={min(limit, 100)}")
        pulls = [dict(i, merged_at=i["pull_request"].get("merged_at")) for i in found if i.get("pull_request")]
    else:
        pulls = api(f"repos/{{owner}}/{{repo}}/pulls?state=all&per_page={min(limit, 100)}")
    for p in pulls:
        state = "OPEN" if p["state"] == "open" else "MERGED" if p.get("merged_at") else "CLOSED"
        if state == "OPEN" and "head" not in p:
            p = dict(p, head=api(f"repos/{{owner}}/{{repo}}/pulls/{p['number']}")["head"])
        # Close reasons live in the comments; only closed changes need them.
        # Who said it travels with what was said: the feed keeps bots out and names each person's role.
        comments = [] if state == "OPEN" else [{"body": c.get("body") or "", "author": {"login": (c.get("user") or {}).get("login", ""),
                                                "type": (c.get("user") or {}).get("type", "")},
                                                "authorAssociation": c.get("author_association", "")} for c in
                                                api(f"repos/{{owner}}/{{repo}}/issues/{p['number']}/comments")]
        rows.append({"number": p["number"], "title": p["title"], "state": state, "mergedAt": p.get("merged_at"),
                     "closedAt": p.get("closed_at"), "comments": comments, "headRefName": (p.get("head") or {}).get("ref"),
                     "url": p.get("html_url")})
    print(json.dumps(rows[:limit]))


def pr_create(args):
    body = open(opt(args, "--body-file")).read()
    p = api("repos/{owner}/{repo}/pulls", "-f", f"title={opt(args, '--title')}", "-f", f"head={opt(args, '--head')}",
            "-f", f"base={opt(args, '--base')}", "-f", f"body={body}", "-F", f"draft={'true' if '--draft' in args else 'false'}",
            method="POST")
    if opt(args, "--label"):
        api(f"repos/{{owner}}/{{repo}}/issues/{p['number']}/labels", "-f", f"labels[]={opt(args, '--label')}", method="POST")
    print(p["html_url"])


def pr_checks(sha):
    runs = api(f"repos/{{owner}}/{{repo}}/commits/{sha}/check-runs?per_page=100")
    status = api(f"repos/{{owner}}/{{repo}}/commits/{sha}/status?per_page=100")
    print(json.dumps({"total": runs["total_count"], "runs": [{"name": r["name"], "status": r["status"], "conclusion": r["conclusion"]}
                                                           for r in runs["check_runs"]],
                      "state": status["state"], "statuses": [{"context": c["context"], "state": c["state"]} for c in status["statuses"]]}))


def issue_list(args):
    found = api(f"repos/{{owner}}/{{repo}}/issues?state={opt(args, '--state', 'open')}&labels={urllib.parse.quote(opt(args, '--label', ''))}&per_page=100")
    print(json.dumps([{"number": i["number"], "body": i.get("body") or ""} for i in found if "pull_request" not in i]))


def issue_create(args):
    i = api("repos/{owner}/{repo}/issues", "-f", f"title={opt(args, '--title')}", "-f", f"body={open(opt(args, '--body-file')).read()}",
            "-f", f"labels[]={opt(args, '--label')}", method="POST")
    print(i["html_url"])


def pr_merge(args):
    # sha= makes GitHub refuse the merge if the head moved after the checks were read.
    r = api(f"repos/{{owner}}/{{repo}}/pulls/{args[2]}/merge", "-f", "merge_method=squash",
            "-f", f"sha={opt(args, '--match-head-commit')}", method="PUT")
    if not r.get("merged"):
        raise SystemExit(f"ghrest: not merged: {r.get('message')}")
    print(r["sha"])


def said(c):
    """Who said it, their tie to the repo, and when: the loop trusts and dates comments by these."""
    u = c.get("user") or {}
    return {"author": {"login": u.get("login", ""), "type": u.get("type", "")}, "authorAssociation": c.get("author_association", ""),
            "createdAt": c.get("submitted_at") or c.get("created_at"), "body": c.get("body") or ""}


def pr_read(what, n):
    base = f"repos/{{owner}}/{{repo}}"
    if what == "info":
        p = api(f"{base}/pulls/{n}")
        print(json.dumps({"number": p["number"], "title": p["title"], "body": p.get("body") or "", "state": p["state"],
                          "draft": p.get("draft", False), "merged": bool(p.get("merged_at")), "author": p["user"]["login"],
                          "head": p["head"]["sha"], "base": p["base"]["ref"], "url": p["html_url"]}))
    elif what == "diff":
        out = subprocess.run([GH, "api", f"{base}/pulls/{n}", "-H", "Accept: application/vnd.github.diff"], capture_output=True, text=True)
        if out.returncode:
            sys.stderr.write(out.stderr)
            raise SystemExit(out.returncode)
        print(out.stdout, end="")
    elif what == "files":
        print("\n".join(f["filename"] for f in api(f"{base}/pulls/{n}/files?per_page=100")))
    elif what == "comments":
        issue = api(f"{base}/issues/{n}/comments?per_page=100")
        review = api(f"{base}/pulls/{n}/comments?per_page=100")
        print(json.dumps([dict(said(c), path=c.get("path")) for c in issue + review]))
    elif what == "reviews":
        print(json.dumps([dict(said(r), state=r["state"]) for r in api(f"{base}/pulls/{n}/reviews?per_page=100")]))


READS = ("info", "diff", "files", "comments", "reviews")


def main(args):
    if args[:1] == ["pr"] and len(args) == 3 and args[1] in READS and args[2].isdigit():
        pr_read(args[1], args[2])
    elif args[:2] == ["pr", "list"]:
        pr_list(args)
    elif args[:2] == ["pr", "create"]:
        pr_create(args)
    elif args[:2] == ["issue", "list"]:
        issue_list(args)
    elif args[:2] == ["issue", "create"]:
        issue_create(args)
    elif args[:2] == ["issue", "comment"] and len(args) > 2 and args[2].isdigit():
        api(f"repos/{{owner}}/{{repo}}/issues/{args[2]}/comments", "-f", f"body={open(opt(args, '--body-file')).read()}", method="POST")
    elif args[:2] == ["pr", "view"]:
        print(api(f"repos/{{owner}}/{{repo}}/pulls/{args[2]}")["head"]["sha"])  # only headRefOid is asked for
    elif args[:2] == ["pr", "base"] and len(args) == 3 and args[2].isdigit():
        ref = api(f"repos/{{owner}}/{{repo}}/pulls/{args[2]}")["base"]["ref"]
        print(api(f"repos/{{owner}}/{{repo}}/git/ref/heads/{ref}")["object"]["sha"])
    elif args[:2] == ["pr", "checks"]:
        pr_checks(args[2])
    elif args[:2] == ["pr", "merge"] and "--squash" in args and "--match-head-commit" in args:
        pr_merge(args)
    elif args[:2] == ["repo", "view"]:
        repo = api("repos/{owner}/{repo}")
        # gh prints PRIVATE, PUBLIC or INTERNAL; the loop reads --json visibility to decide what a pull request may say
        print(repo["visibility"].upper() if "visibility" in args else repo["html_url"])
    elif args[:2] == ["label", "create"]:
        try:
            subprocess.run([GH, "api", "repos/{owner}/{repo}/labels", "-X", "POST", "-f", f"name={args[2]}"], capture_output=True,
                           stdin=subprocess.DEVNULL, timeout=TIMEOUT)  # it may already exist
        except subprocess.TimeoutExpired:
            pass
    else:
        sys.exit(f"ghrest: unsupported: {' '.join(args)}")


if __name__ == "__main__":
    main(sys.argv[1:])
