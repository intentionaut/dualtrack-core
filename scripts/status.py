#!/usr/bin/env python3
"""Where this repo stands with its team, and the one next step, the same way every visit.

Usage: python3 <kit>/scripts/status.py      from the root of the product repo

Pulls the state repo first, when there is one. Prints `profile:` and `context:` paths, `state: <setup|pr|question|decisions|failed|blocked|waiting_for_decision|safety_stop|idle>`, then
`next:` in plain words, then at most one `offer:` line. The /dualtrack:dualtrack skill reads these out.
"""
import json
import os
import re
import profile_value  # noqa: E402
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import decide
import loop_lib

GH = os.environ.get("GH_BIN", "gh")


def read(path):
    try:
        return open(path, errors="replace").read()
    except OSError:
        return ""


def field(profile, name):
    return profile_value.field(profile, name)


PR_URL = r"https://github\.com/([^\s/)>\]]+/[^\s/)>\]]+)/pull/\d+(?!\d)"


def origin_repo():
    """owner/name from origin, lower-cased; empty when there is no GitHub origin."""
    r = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True)
    m = re.search(r"github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?/?$", r.stdout.strip())
    return m[1].lower() if m else ""


def logged_pr(morning, log):
    """First PR URL in morning.md that team-log.md also holds in full and that belongs to this repo. Morning.md quotes outside text."""
    home = origin_repo()
    held = {m[0] for m in re.finditer(PR_URL, log)}
    return next((m[0] for m in re.finditer(PR_URL, morning) if home and m[1].lower() == home and m[0] in held), None)


def state(profile_text, context):
    """(state, next step), from the records, first match wins."""
    morning = read(os.path.join(context, "morning.md"))
    pr = logged_pr(morning, read(os.path.join(context, "team-log.md")))
    if pr:
        r = subprocess.run([GH, "pr", "view", pr, "--json", "state", "-q", ".state"], capture_output=True, text=True)
        if r.stdout.strip() == "OPEN":
            return "pr", f"Review {pr}: merge it, comment on it to ask for changes, or close it with a one-line reason."
    try:
        brief = json.load(open(os.path.join(context, "options.json")))
    except (OSError, ValueError):
        brief = {}
    done = answered(context, brief)
    if brief.get("question") and not done:
        return "question", f"Answer Dualtrack's question: {brief['question']}"
    if brief.get("options") and not done:
        return "decisions", "Pick one of the options in morning.md, or say none of these and why."
    # A run that did not pass says so, with the step that fits it, until a later run passes or the owner's call is recorded.
    day, outcome, row = loop_lib.last_run(context)
    if row and row["state"] != loop_lib.PASS and not (row["state"] == loop_lib.WAITING and called_since(context, day)):
        return row["state"], f"{row['next']} Last run: {outcome}".strip()
    last = [l for l in read(os.path.join(context, "team-log.md")).splitlines() if l.startswith("- ")]
    return "idle", f"Last run: {last[-1][2:]}" if last else "Dualtrack agents have not run yet."


def called_since(context, day):
    """True when the owner has made a call (an answer, a pick, an allow, a resume) on or after the day of the last run."""
    allowed = re.findall(r"^- (\d{4}-\d\d-\d\d) \|.*\| allowed by owner", read(os.path.join(context, "allowed.md")), re.M)
    return answered(context, {"date": day}) or any(d >= day for d in allowed)


def answered(context, brief):
    """True when an owner's call already answers this brief. The dashboard asks the same thing."""
    # An owner's call dated on or after the brief answers it. Only decide.py's shapes count: the loop's own
    # lines (a merge it read back, a started bet) carry the same date and answer nothing.
    bets = read(os.path.join(context, "bets.md"))
    gone = loop_lib.withdrawn(bets)  # a pick the owner took back no longer answers the brief
    bets = "\n".join(l for l in bets.splitlines() if not ("| confirmed by owner" in l and loop_lib.bet_title(l.split("|")[1]) in gone))
    calls = loop_lib.owner_lines(read(os.path.join(context, "decisions.md")) + "\n" + bets)
    return any(d >= brief.get("date", "9") for d in re.findall(
        r"^- (\d{4}-\d\d-\d\d) \|.*(?:by owner|owner answer to:|\| owner \| resume|started: resolved:)", calls, re.M))


def offer(profile, profile_text, context):
    """At most one step up, when the record shows the owner is ready."""
    runs = sum(1 for l in read(os.path.join(context, "team-log.md")).splitlines() if re.match(r"- \d{4}-", l))
    numbers = read(os.path.join(os.path.dirname(profile), "numbers.md"))
    if runs >= 3 and not field(profile_text, "Sources") and not re.search(r"\d", numbers):
        return "connect: three runs with no sources or numbers. Offer /dualtrack:dualtrack-connect, or to paste this week's numbers."
    outcomes = re.findall(r"^- \S+ \| #(\d+) .*\| (yes|no):", read(os.path.join(context, "decisions.md")), re.M)[-5:]
    asked = {l.split("\t")[0].lstrip("#") for l in read(os.path.join(context, "asked.md")).splitlines()}
    if len(outcomes) == 5 and all(ok == "yes" and n not in asked for n, ok in outcomes):
        if field(profile_text, "Code review") != "on":
            return "code review: five merged pull requests in a row, none with changes asked. Offer Code Review."
        if field(profile_text, "Auto-merge") != "on":
            return "auto-merge: five merged pull requests in a row with Code Review on. Offer Auto-merge."
    return ""


def main():
    profile = decide.find_profile()
    if not os.path.exists(profile):
        print("state: setup\nnext: Set this repo up with the setup skill.")
        return 0
    text = read(profile)
    repo = field(text, "State repo")
    if repo and subprocess.run(["git", "-C", repo, "remote"], capture_output=True, text=True).stdout.strip():
        pulled = decide.net(["git", "-C", repo, "pull", "-q"], default=30).returncode == 0
        if not pulled:
            print(f"warning: could not pull {loop_lib.oneline(repo)}, so a cloud run's latest results may be missing")
    context = decide.context_path(profile)
    name, step = state(text, context)
    one = loop_lib.oneline
    print(f"profile: {one(profile)}\ncontext: {one(context)}\nstate: {name}\nnext: {one(step)}")
    # A pick nobody has built yet: showing it lets the owner spot one they never made.
    queued = loop_lib.confirmed(read(os.path.join(context, "bets.md")))
    if queued:
        print(f"Next run builds: {loop_lib.oneline(queued)}")
    extra = offer(profile, text, context)
    if extra:
        print(f"offer: {loop_lib.oneline(extra)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
