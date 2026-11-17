#!/usr/bin/env python3
"""Summarise how Dualtrack agents have done, from the record it already keeps. Sends nothing.

Run from the folder that holds profile.md:

  python3 ../dualtrack/scripts/stats.py

It reads team-log.md and decisions.md in your Context path and prints counts only:
no product names, titles, reasons, code or links.

To send them to the kit's author, by your choice:

  stats.py --share          ask how to send: a GitHub issue, an email, or print only
  stats.py --share issue    open a new GitHub issue in your browser, filled in
  stats.py --share email    open your email app with a message, filled in

Nothing is sent until you press submit or send yourself.
"""
import os
import re
import json
import statistics
import sys
import urllib.parse
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decide import context_path
import loop_lib

UNKNOWN = "a line this version does not recognise"  # shown, never folded into an error count


def label(outcome):
    """What a run did, in the words of the gate table (loop_lib.GATES), so stats and the brief agree."""
    row = loop_lib.gate(outcome)
    return row["label"] if row else UNKNOWN


def read(path):
    try:
        return open(path).read()
    except OSError:
        return ""


def stats(log, decisions):
    runs = re.findall(r"^- (\d{4}-\d\d-\d\d) \| (.*) \| \$([\d.]+)\s*$", log, re.M)
    kinds = {}
    for _, outcome, _ in runs:
        kinds[label(outcome)] = kinds.get(label(outcome), 0) + 1
    costs = [float(c) for *_, c in runs]

    # Review rounds per pull request, from the "opened" and "merged" lines:
    # "/pull/7, navigator CHANGES APPROVE ux APPROVE", then optionally " code review APPROVE, ...".
    reviewed, auto = {}, set()
    for _, outcome, _ in runs:
        m = re.search(r"/pull/(\d+), (?:commit \w+, )?navigator ([A-Z ]+?)(?: ux ([A-Z ]*?))?\s*(?:code review|$)", outcome)
        if m:
            reviewed[m[1]] = (m[2].split(), (m[3] or "").split())
            if outcome.startswith("merged"):
                auto.add(m[1])
    # The owner's outcome per pull request, from decisions.md: "#7 title | yes: merged" or "| no: reason".
    closed = dict(re.findall(r"^- \S+ \| #(\d+) .*\| (yes|no):", decisions, re.M))

    caught = sum(1 for nav, ux in reviewed.values() if "CHANGES" in nav + ux)
    approved_then_closed = sum(1 for n in reviewed if closed.get(n) == "no")
    return {
        "since": runs[0][0] if runs else None,
        "runs": len(runs),
        "kinds": kinds,
        "cost_total": sum(costs),
        "cost_median": statistics.median(costs) if costs else 0.0,
        "opened": len(reviewed),
        "merged": sum(1 for n in reviewed if closed.get(n) == "yes" and n not in auto),
        "auto_merged": len(auto),
        "closed": approved_then_closed,
        "open": sum(1 for n in reviewed if n not in closed),
        "caught": caught,
        "declined": len(re.findall(r"\| rejected by owner:", decisions)),
        "answered": len(re.findall(r"\| owner answer to:", decisions)),
    }


def report(s, picked):
    if not s["runs"]:
        return "No runs recorded yet. Run Dualtrack once, then try again.\n"
    lines = [
        "Dualtrack: stats",
        f"Since {s['since']}: {s['runs']} runs",
        "",
        "What each run did:",
        *[f"  {n:>3}  {what}" for what, n in s["kinds"].items() if n],
        "",
        "Changes built for review:",
        f"  {s['opened']:>3}  opened",
        f"  {s['merged']:>3}  merged by you",
        *([f"  {s['auto_merged']:>3}  merged by Dualtrack agents (Auto-merge)"] if s["auto_merged"] else []),
        f"  {s['closed']:>3}  closed by you without merging",
        f"  {s['open']:>3}  still open",
        "",
        "Review:",
        f"  {s['caught']:>3}  sent back by a reviewer before you saw them",
        f"  {s['closed']:>3}  approved by the reviewers, then closed by you",
        "       (the nearest measure of what review missed; some are",
        "        simply changes you did not want)",
        "",
        "Your input:",
        f"  {picked:>3}  options you picked",
        f"  {s['declined']:>3}  options you declined",
        f"  {s['answered']:>3}  questions you answered",
        "",
        f"Estimated usage: ${s['cost_total']:.2f} in total, ${s['cost_median']:.2f} for a typical run",
        "",
        "Counts only: no product names, titles, reasons, code or links.",
    ]
    return "\n".join(lines) + "\n"


def destinations():
    """Where feedback can go, from the kit's feedback.json. An empty field hides that choice."""
    try:
        d = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "feedback.json")))
    except (OSError, ValueError):
        d = {}
    return {k: v for k, v in (("issue", d.get("issues_url", "")), ("email", d.get("email", ""))) if v}


def share_url(how, where, text, title="Dualtrack stats"):
    if how == "issue":
        return f"{where.rstrip('/')}/new?" + urllib.parse.urlencode({"title": title, "body": text})
    return f"mailto:{where}?" + urllib.parse.urlencode({"subject": title, "body": text}, quote_via=urllib.parse.quote)


def choose(options):
    """Ask once, in a terminal only. Returns issue, email or None."""
    if not sys.stdin.isatty():
        return None
    names = {"issue": "Open a GitHub issue in your browser", "email": "Open an email in your mail app"}
    menu = list(options) + [None]
    for n, key in enumerate(menu, 1):
        print(f"  {n}. {names.get(key, 'Print only, send nothing')}")
    answer = input("Send how? ").strip()
    return menu[int(answer) - 1] if answer.isdigit() and 1 <= int(answer) <= len(menu) else None


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    context = context_path()
    s = stats(read(os.path.join(context, "team-log.md")), read(os.path.join(context, "decisions.md")))
    bets = read(os.path.join(context, "bets.md"))
    picked = len(re.findall(r"\| confirmed by owner", bets)) - len(re.findall(r"\| withdrawn: ", bets))
    text = report(s, picked)
    sys.stdout.write(text)
    if not argv or argv[0] != "--share" or not s["runs"]:
        if s["runs"] and destinations():
            sys.stdout.write("\nTo send these to the kit's author, run it again with --share.\n")
        return 0
    options = destinations()
    if not options:
        sys.stdout.write("\nThis copy of the kit names nowhere to send feedback. Copy the text above instead.\n")
        return 0
    how = argv[1] if len(argv) > 1 else choose(options)
    if how not in options:
        sys.stdout.write("\nNothing sent.\n" if how is None else f"\nCannot share by {how}. Choose from: {', '.join(options)}.\n")
        return 0 if how is None else 2
    url = share_url(how, options[how], text)
    opened = webbrowser.open(url)
    where = "your browser" if how == "issue" else "your email app"
    sys.stdout.write(f"\nOpened {where} with the stats filled in. Nothing is sent until you submit it.\n" if opened
                     else f"\nCould not open {where}. Open this link yourself:\n{url}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
