#!/usr/bin/env python3
"""One table across every product in a state repo. Reads the record, changes nothing, calls no agent.

Usage: python3 scripts/portfolio.py <state repo>
"""
import json
import os
import pathlib
import profile_value  # noqa: E402
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import loop_lib


def read(path):
    try:
        return pathlib.Path(path).read_text()
    except OSError:
        return ""


def row(folder):
    profile = read(folder / "profile.md")
    m = profile_value.field(profile, "Context path")
    # Context paths are relative to the product repo, which sits beside the state repo.
    context = folder / "product-context" if not m else (folder.parent.parent / folder.name / m).resolve()
    runs = [l for l in read(context / "team-log.md").splitlines() if l.startswith("- ")]
    last = [c.strip() for c in runs[-1][2:].split("|")] if runs else []
    try:
        brief = json.loads(read(context / "options.json"))
    except ValueError:
        brief = {}
    waiting = len(brief.get("options", []))
    bets = loop_lib.open_titles(read(context / "bets.md"))
    clean = lambda s: s.replace("|", "/")
    return [folder.name, f"{last[0]}: {clean(last[1])}" if len(last) > 1 else "no run yet",
            "; ".join(clean(b) for b in bets) or "none",
            f"{waiting} from {brief.get('date', '?')}" if waiting else "none", clean(brief.get("question") or "") or "none"]


def main(argv):
    if not argv:
        print(__doc__.strip())
        return 2
    state = pathlib.Path(argv[0])
    products = sorted(p.parent for p in state.glob("*/profile.md"))
    if not products:
        print(f"no products in {state}: each one is a folder with a profile.md")
        return 3
    print("| Product | Last run | Picked, not built yet | Options waiting for you | Question for you |")
    print("|---|---|---|---|---|")
    for p in products:
        print("| " + " | ".join(row(p)) + " |")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
