#!/usr/bin/env python3
"""Run the test suite split across several processes.

CI bills per job minute and the suite is one long serial run, mostly in
test_loop.py, so splitting by file does not help: the split is by test. Every
test id under tests/ is dealt round-robin into TEST_WORKERS shards, and each
shard runs as `python3 -m unittest <ids>` from the repo root, as discover would.

SHARD="i/N" (0-based i) keeps only every Nth test id (sorted, index % N == i), so
several CI jobs can each run a slice; the slices together cover every test once.

Fails closed: a failing shard fails the run, and so does any difference
between the number of tests found and the number that ran.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
RAN = re.compile(r"^Ran (\d+) tests? in ([\d.]+)s", re.M)


def ids(suite):
    for t in suite:
        if isinstance(t, unittest.TestSuite):
            yield from ids(t)
        else:
            yield t.id()


def select(found, spec):
    """The ids a CI shard runs. spec is "i/N" with 0 <= i < N, or empty for all. Raises ValueError if malformed."""
    if not spec:
        return list(found)
    m = re.fullmatch(r"(\d+)/(\d+)", spec)
    if not m or not 0 <= int(m[1]) < int(m[2]):
        raise ValueError(f"SHARD must look like i/N with 0 <= i < N, got {spec!r}")
    i, n = int(m[1]), int(m[2])
    return [t for k, t in enumerate(sorted(found)) if k % n == i]


def run(shard):
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(TESTS), os.environ.get("PYTHONPATH")]))}
    r = subprocess.run([sys.executable, "-m", "unittest", *shard], cwd=ROOT, env=env, capture_output=True, text=True)
    out = r.stdout + r.stderr
    m = RAN.search(out)
    return r.returncode, int(m.group(1)) if m else 0, float(m.group(2)) if m else 0.0, out


def main() -> int:
    # Same import roots as `python3 -m unittest discover -s tests` run from the repo root.
    sys.path[:0] = [str(TESTS), str(ROOT)]
    os.chdir(ROOT)
    # Tests make folders in $TMPDIR; a fresh one per run is removed at the end, so nothing piles up between runs.
    scratch = tempfile.mkdtemp(prefix="dualtrack-tests-")
    os.environ["TMPDIR"] = scratch
    try:
        return run_all()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def run_all() -> int:
    suite = unittest.defaultTestLoader.discover(str(TESTS), top_level_dir=str(TESTS))
    found = list(ids(suite))
    broken = [i for i in found if i.startswith("unittest.loader.")]
    if not found or broken:
        print(f"FAIL: {len(found)} tests found; import failures: {broken}")
        return 1
    total = len(found)
    try:
        found = select(found, os.environ.get("SHARD", ""))
    except ValueError as e:
        print(f"FAIL: {e}")
        return 1
    if os.environ.get("SHARD"):
        print(f"shard {os.environ['SHARD']}: {len(found)} of {total} tests")
    if not found:
        print("FAIL: this shard selected no tests")
        return 1
    workers = int(os.environ.get("TEST_WORKERS") or os.cpu_count() or 2)
    shards = [found[i::workers] for i in range(workers) if found[i::workers]]
    with ThreadPoolExecutor(max_workers=len(shards)) as pool:
        results = list(pool.map(run, shards))
    ran = sum(r[1] for r in results)
    bad = [r for r in results if r[0] != 0]
    for i, (code, n, secs, _) in enumerate(results):
        print(f"{'FAIL' if code else 'ok  '} shard {i}: {n} tests in {secs:.1f}s")
    for code, _, _, out in bad:
        print(f"\n===== failing shard, exit {code} =====\n{out}")
    print(f"\n{ran} of {len(found)} tests ran in {len(shards)} shards")
    if ran != len(found):
        print("FAIL: tests found and tests run differ")
        return 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
