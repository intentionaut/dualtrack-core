#!/usr/bin/env python3
"""Pick the tests a change touches (INT-248).

`affected.py BASE` prints one line, "mode: full (why)" or "mode: affected (why)", and for affected mode a second line
of test module names. test_parallel.py calls plan() directly for `--changed BASE`.

The map is tests/affected.json: {"safety": [modules that always run], "critical": [more tests that always run],
"nightly": [tests a pull request run skips], "map": {glob: [modules]}}. Globs use fnmatch,
so `*` also crosses `/`. A file is mapped if any glob matches it, even a glob with no modules (docs).
The safety set and the critical list run in every affected-mode run. The nightly list is not used here: test_parallel.py
drops those tests from an affected-mode `--changed` run. A "mode: full" run (this file cannot tell) and the nightly run
(no `--changed`) run them.

Fails safe: every case it cannot place runs the whole suite (mods is None). That is a changed file no glob matches,
a change to the machinery itself, a diff that cannot be computed, a missing base, no changed files, a bad map.
"""
import fnmatch
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAP = ROOT / "tests" / "affected.json"
# Deliberately hard-coded, not read from the map: a bad map edit cannot turn these off.
ALWAYS_FULL = {"scripts/daily_loop.sh", "tests/affected.json", "scripts/affected.py", "scripts/build_affected_map.py",
               "scripts/test_parallel.py"}
ALWAYS_FULL_PREFIX = (".github/workflows/",)


def valid(amap):
    return (isinstance(amap, dict) and isinstance(amap.get("safety"), list) and amap["safety"]
            and isinstance(amap.get("map"), dict) and amap["map"]
            and all(isinstance(amap.get(k, []), list) for k in ("critical", "nightly")))


def choose(changed, amap):
    """(modules, why). modules is None for "run everything"."""
    if not valid(amap):
        return None, "the map is missing or malformed"
    if not changed:
        return None, "no changed files found"
    for f in changed:
        if f in ALWAYS_FULL or f.startswith(ALWAYS_FULL_PREFIX):
            return None, f"{f} changed, and a change to the test machinery runs everything"
    mods = set(amap["safety"]) | set(amap.get("critical", []))
    for f in changed:
        hits = [g for g in amap["map"] if fnmatch.fnmatchcase(f, g)]
        if not hits:
            return None, f"{f} matches no glob in the map"
        for g in hits:
            mods.update(amap["map"][g])
    return sorted(mods), f"{len(changed)} changed file(s) reach {len(mods)} affected test modules, safety and critical sets included"


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def changed_files(base, root=ROOT):
    """Files changed since the merge base with `base`, both names for a rename. Raises ValueError if that cannot be known."""
    if not base:
        raise ValueError("no base given")
    if git(root, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}").returncode != 0:
        raise ValueError(f"base {base!r} is missing")
    r = git(root, "diff", "--name-only", "--no-renames", f"{base}...HEAD")
    if r.returncode != 0:
        raise ValueError(f"diff against {base!r} failed: {r.stderr.strip()[:200]}")
    return [line for line in r.stdout.splitlines() if line]


def plan(base, amap=None, root=ROOT):
    """(modules or None, why). None means run everything."""
    try:
        if amap is None:
            amap = json.loads(MAP.read_text())
        changed = changed_files(base, root)
    except (OSError, ValueError) as e:  # json.JSONDecodeError is a ValueError
        return None, str(e)
    return choose(changed, amap)


def main(argv):
    if len(argv) != 2:
        print("usage: affected.py BASE")
        return 2
    mods, why = plan(argv[1])
    print(f"mode: {'full' if mods is None else 'affected'} ({why})")
    if mods is not None:
        print(" ".join(mods))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
