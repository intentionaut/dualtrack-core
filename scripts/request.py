#!/usr/bin/env python3
"""Ask the kit's author for a feature, or tell them about a gap. Sends nothing by itself.

  python3 ../dualtrack/scripts/request.py                     ask what you want, then how to send it
  python3 ../dualtrack/scripts/request.py "what you want"     the same, with the request given
  python3 ../dualtrack/scripts/request.py --share issue "..." open a filled-in GitHub issue in your browser
  python3 ../dualtrack/scripts/request.py --share email "..." open your email app with it filled in

The message holds your words and the kit's version, nothing else. Nothing is sent until you submit it.
"""
import json
import os
import sys
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stats import choose, destinations, share_url

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def version():
    try:
        return json.load(open(os.path.join(KIT, ".claude-plugin", "plugin.json")))["version"]
    except (OSError, ValueError, KeyError):
        return "unknown"


def message(want):
    return f"{want.strip()}\n\nDualtrack {version()}\n"


def title(want):
    first = " ".join(want.split())
    return "Kit request: " + (first if len(first) <= 60 else first[:57].rstrip() + "...")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    how = None
    if argv[:1] == ["--share"]:
        how, argv = (argv[1] if len(argv) > 1 else None), argv[2:]
    want = " ".join(argv).strip()
    if not want and sys.stdin.isatty():
        want = input("What should Dualtrack do that it does not? ").strip()
    if not want:
        sys.stdout.write("Nothing to send: say what you want, for example: request.py \"take comments on pull requests\"\n")
        return 2
    options = destinations()
    if not options:
        sys.stdout.write("This copy of the kit names nowhere to send requests. Copy this instead:\n\n" + message(want))
        return 0
    how = how or choose(options)
    if how not in options:
        sys.stdout.write("\nNothing sent.\n" if how is None else f"\nCannot send by {how}. Choose from: {', '.join(options)}.\n")
        return 0 if how is None else 2
    url = share_url(how, options[how], message(want), title(want))
    where = "your browser" if how == "issue" else "your email app"
    sys.stdout.write(f"Opened {where} with your request filled in. Nothing is sent until you submit it.\n" if webbrowser.open(url)
                     else f"Could not open {where}. Open this link yourself:\n{url}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
