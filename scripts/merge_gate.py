#!/usr/bin/env python3
"""Decide whether Dualtrack agents may merge their own ready pull request. A script decides, never an agent.

Usage: merge_gate.py <profile> <run_dir> <pr_number> <head_sha>
Reads from run_dir: item.json, intent.md, diff.txt (name-status), numstat.txt, tests.result, navigator.txt,
ux-review.txt, code-review.txt, and screens.txt when the repo has a web surface.
Prints `merged <sha>` (exit 0), or `left for the owner: <the check that failed>` (exit 4).
Anything it cannot read fails closed. Env: GH (default ghrest.py), CI_WAIT seconds (default 600), CI_POLL (30).
"""
import json
import os
import re
import profile_value  # noqa: E402
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from loop_lib import lane, protected  # noqa: E402

GH = os.environ.get("GH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "ghrest.py")
MAX_LINES, MAX_FILES, MAX_BYTES = 50, 3, 20000
# Files whose change reaches past the code: what installs, builds, deploys or configures it.
RISKY = {
    "a dependency manifest": r"(^|/)(package\.json|requirements[^/]*\.txt|pyproject\.toml|setup\.(py|cfg)|Pipfile|Gemfile|go\.mod|Cargo\.toml|composer\.json|pom\.xml|build\.gradle[^/]*|[^/]+\.gemspec)$",
    "a lockfile": r"(^|/)([^/]+\.lock|package-lock\.json|npm-shrinkwrap\.json|pnpm-lock\.yaml|go\.sum)$",
    "a migration": r"migrat|(^|/)schema[^/]*$|\.sql$",
    "CI": r"^\.github(/|$)|(^|/)\.gitlab-ci\.yml$|(^|/)\.circleci/|(^|/)Jenkinsfile$|(^|/)\.buildkite/",
    "deploy": r"(^|/)(Dockerfile[^/]*|docker-compose[^/]*|vercel\.json|netlify\.toml|fly\.toml|Procfile|render\.yaml|app\.yaml|wrangler\.toml)$|(^|/)(deploy|k8s|helm|terraform)/|\.tf$|(^|/)[^/]*deploy[^/]*\.(sh|bash|py|[cm]?[jt]s)$",
    "agent instructions": r"(^|/)(CLAUDE|AGENTS|GEMINI)\.md$|(^|/)\.cursorrules$|(^|/)\.cursor/",
    "tool config": r"(^|/)(\.mcp\.json|\.npmrc|\.yarnrc|\.pypirc)$|(^|/)\.husky(/|$)",
    "the test harness": r"(^|/)conftest\.py$",
    "a snapshot, which would make whatever the code prints the expected value": r"\.snap$|(^|/)__snapshots__/",
    "an agent prompt": r"(^|/)(agents|standards)/[^/]+\.md$|(^|/)skills/[^/]+/SKILL\.md$",
    "a hook": r"(^|/)\.?githooks(/|$)|(^|/)hooks(/|$)",
    "code that runs on its own (editor tasks, dev containers, task runners, Python start-up)":
        r"(^|/)(\.devcontainer|\.vscode)/|(^|/)(justfile|Justfile|Taskfile[^/]*|noxfile\.py|sitecustomize\.py|usercustomize\.py)$|\.pth$",
    "a safety file": r"(^|/)(safety-files\.json|egress_proxy\.py|tamper\.py)$",
    "code owners": r"(^|/)CODEOWNERS$",
    "the merge gate": r"(^|/)(merge_gate|loop_lib|daily_loop|test_merge_gate)\.(py|sh)$",
    "config": r"(^|/)\.env|(^|/)\.claude/|(^|/)config/|\.config\.[cm]?[jt]s$|\.(ya?ml|toml|ini|cfg|conf)$|(^|/)(tsconfig[^/]*\.json|\.eslintrc[^/]*|\.prettierrc[^/]*|settings\.json|Makefile)$",
}


class Fail(Exception):
    pass


def read(run, name):
    try:
        return open(os.path.join(run, name)).read()
    except OSError:
        raise Fail(f"unreadable: {name}")


def field(profile, name):
    return profile_value.field(profile, name)


def risky(path):
    return next((what for what, pattern in RISKY.items() if re.search(pattern, path, re.I)), None)


def green(checks, required):
    """True only when every check run and status succeeded and each required check is among them.
    Skipped and neutral are not success: a workflow whose jobs all skip ran no tests."""
    runs, statuses = checks["runs"], checks["statuses"]
    if checks["total"] != len(runs) or not required:
        return False
    names = {r["name"] for r in runs} | {c["context"] for c in statuses}
    ok_runs = all(r["status"] == "completed" and r["conclusion"] == "success" for r in runs)
    return required <= names and ok_runs and (not statuses or checks["state"] == "success")


def gh(*args):
    r = subprocess.run([GH, *args], capture_output=True, text=True)
    if r.returncode:
        raise Fail(f"unreadable: gh {' '.join(args[:2])}: {r.stderr.strip()[-200:]}")
    return r.stdout.strip()


def ci(pr, sha, required):
    head = gh("pr", "view", pr, "--json", "headRefOid", "-q", ".headRefOid")
    if head != sha:
        raise Fail(f"the pull request head is {head[:7]}, not the reviewed {sha[:7]}")
    deadline = time.time() + float(os.environ.get("CI_WAIT", "600"))
    while True:
        try:
            checks = json.loads(gh("pr", "checks", sha))
            # GitHub reports a commit with no statuses as pending, so only real statuses can keep it waiting.
            done = all(r["status"] == "completed" for r in checks["runs"]) and (not checks["statuses"] or checks["state"] != "pending")
        except (ValueError, KeyError, TypeError):
            raise Fail("unreadable: CI checks")
        if green(checks, required):
            return
        if (done and (checks["runs"] or checks["statuses"])) or time.time() >= deadline:
            raise Fail(f"CI is not green on {sha[:7]}")
        time.sleep(float(os.environ.get("CI_POLL", "30")))


def gate(profile, run, pr, sha):
    # Company mode: the repo's own rulesets and a human reviewer decide every merge, never this script.
    if field(profile, "Company mode").lower().split(" ")[:1] == ["on"]:
        raise Fail("company mode: a person merges, under the repo's own rules")
    if field(profile, "Auto-merge").lower().split(" ")[:1] != ["on"]:
        raise Fail("auto-merge is off")
    names = [l.split("\t")[-1] for l in read(run, "diff.txt").splitlines() if l.strip()]
    if not names:
        raise Fail("unreadable: diff.txt is empty")
    paths_only = "\n".join(re.findall(r"^\*\*Protected path:\*\*.*$", profile, re.M))
    hit = protected(paths_only, names, lambda p: "")
    if hit:
        raise Fail(f"it touches a {hit}")
    for name in names:
        what = risky(name)
        if what:
            raise Fail(f"it touches {what}: {name}")
    lines = 0
    for row in read(run, "numstat.txt").splitlines():
        added, deleted = row.split("\t")[:2]
        if not (added.isdigit() and deleted.isdigit()):
            raise Fail(f"unreadable: line count for {row.split(chr(9))[-1]}")
        lines += int(added) + int(deleted)
    if len(names) > MAX_FILES or lines > MAX_LINES:
        raise Fail(f"{lines} lines in {len(names)} files, over {MAX_LINES} lines or {MAX_FILES} files")
    # Lines can be any length, and a symlink or a mode change is one line or none.
    patch = read(run, "diff.patch")
    if len(patch.encode()) > MAX_BYTES:
        raise Fail(f"the diff is {len(patch.encode())} bytes, over {MAX_BYTES}")
    mode = re.search(r"^(?:new file mode 1[02]0755|(?:new file |deleted file |old |new )mode 120000|old mode |new mode ).*$", patch, re.M)
    if mode:
        raise Fail(f"it changes a file mode or a symlink: {mode[0]}")
    # A run the intent check never reached has no intent.md, and so no line left for after merge.
    if os.path.exists(os.path.join(run, "intent.md")) and re.search(r": AFTER MERGE: ", read(run, "intent.md")):
        raise Fail("a Done when line is checked after merge, on the live site")
    for role, name in (("navigator", "navigator.txt"), ("UX review", "ux-review.txt"), ("Code Review", "code-review.txt")):
        first = (read(run, name).splitlines() or [""])[0].strip()
        if first != "APPROVE":
            raise Fail(f"{role} did not approve: {first or 'no verdict'}")
    try:
        visible = json.loads(read(run, "item.json")).get("visible", True) is not False
    except ValueError:
        raise Fail("unreadable: item.json")
    # The flag comes from the PM and skips design and UX review: the diff decides what a visitor sees, not the flag.
    seen = lane(profile, read(run, "diff.txt")) if not visible else None
    if seen:
        raise Fail(f"it touches {seen}, which a visitor would see, but was planned as not visible")
    if "web" in re.split(r"[^a-z]+", field(profile, "Surfaces").lower()) and visible:
        first = (read(run, "screens.txt").splitlines() or [""])[0].strip()
        if first != "passed":
            raise Fail(f"the screenshot check did not pass: {first or 'not run'}")
    result = read(run, "tests.result").strip()
    # Main already failed these tests: "no new failures" is proof the change broke nothing more, not that the tests pass.
    if result == "no new failures":
        raise Fail("the tests fail the same way on main (no new failures), so a person merges it")
    if result != "passed":
        raise Fail("the tests did not pass")
    # With the code put back the new tests must fail. An install that failed there, or tests that never ran, proves nothing.
    first = read(run, "first.result").strip()
    if first not in ("failed", "not needed"):
        raise Fail(f"the tests did not fail with the code put back ({first or 'no result'}), so they may not show the change")
    # GitHub registers check suites one by one, so the gate waits for named checks, not whatever has appeared.
    required = {n.strip() for n in field(profile, "Required checks").split(",") if n.strip() and "<" not in n}
    if not required:
        raise Fail("the profile names no Required checks")
    # The reviewers judged the change on the base the run started from: a base that moved since is a change nobody reviewed.
    base = read(run, "base.sha").strip()
    if gh("pr", "base", pr) != base:
        raise Fail(f"main moved since the review, from {base[:7]}")
    ci(pr, sha, required)
    merged = gh("pr", "merge", pr, "--squash", "--match-head-commit", sha)
    if not re.fullmatch(r"[0-9a-f]{40}", merged):
        raise Fail(f"unreadable: merge result {merged[:60]}")
    return merged


def main(argv):
    try:
        profile = open(argv[0]).read()
        print(f"merged {gate(profile, *argv[1:4])}")
        return 0
    except (Fail, OSError) as e:
        print(f"left for the owner: {e}")
        return 4


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
