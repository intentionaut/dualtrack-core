#!/usr/bin/env python3
"""Check that Dualtrack's safety files are the ones this release shipped.

  tamper.py check [kit]   at the start of every run: exit 4 and say which file changed
  tamper.py pin [kit]     rewrite safety-files.json from the files, when a release or a change to one of them is made

safety-files.json lists each file and its SHA-256. The list is in the open and the README names every file in it.
A change to any of them stops the run before anything is built: a modified kit is not Dualtrack.
"""
import glob
import hashlib
import json
import os
import subprocess
import sys

MANIFEST = "safety-files.json"
# Everything that runs or instructs: the agents and standards (the harm rule), every script (the stop list, the sandbox,
# the egress proxy, the merge gate, this check), the read-only source list, the hooks and the skills.
PATTERNS = ["agents/*.md", "standards/*.md", "scripts/*.py", "scripts/*.sh", "sources.json", "hooks/*.json", "skills/*/SKILL.md"]


def digest(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def current(kit):
    found = sorted(p for pat in PATTERNS for p in glob.glob(os.path.join(kit, pat)))
    return {os.path.relpath(p, kit): digest(p) for p in found}


def changed(kit):
    """The files that differ from the release's list: edited, missing or added."""
    try:
        with open(os.path.join(kit, MANIFEST)) as f:
            pinned = json.load(f)["files"]
    except (OSError, ValueError, KeyError):
        return [MANIFEST]  # no list to check against: fail closed
    now = current(kit)
    out = {k for k in set(pinned) | set(now) if pinned.get(k) != now.get(k)}
    # In a git checkout the list must also be the one committed: editing a file and its hash together, uncommitted, is still a change.
    committed = subprocess.run(["git", "-C", kit, "show", f"HEAD:{MANIFEST}"], capture_output=True, text=True)
    if committed.returncode == 0:
        try:
            head = json.loads(committed.stdout)["files"]
        except (ValueError, KeyError):
            return [MANIFEST]
        out |= {k for k in set(head) | set(pinned) if head.get(k) != pinned.get(k)}
    return sorted(out)


def message(files):
    names = ", ".join(files)
    return (f"safety stop: {names} changed since this release of Dualtrack. A modified kit is not Dualtrack, so nothing ran "
            "and nothing in your product changed. Put the file back (for example `git checkout -- <file>`) or install Dualtrack again.")


def main(argv):
    cmd = argv[0] if argv else ""
    kit = argv[1] if len(argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if cmd == "pin":
        with open(os.path.join(kit, MANIFEST), "w") as f:
            json.dump({"files": current(kit)}, f, indent=2); f.write("\n")
        return 0
    if cmd == "check":
        files = changed(kit)
        if files:
            print(message(files))
            return 4
        return 0
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
