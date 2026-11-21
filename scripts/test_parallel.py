#!/usr/bin/env python3
"""Run the test suite split across several processes.

CI bills per job minute and the suite is one long serial run, mostly in
test_loop.py, so splitting by file does not help: the split is by test.

Inside a run, the test ids go into a shared queue of small batches and each worker
takes the next batch when it is free, so one slow batch cannot hold up the rest. A batch
is one `scripts/unit_batch.py <ids>` process, run from the repo root as `unittest` would
run it. With tests/durations.json the queue is longest-first and batches are sized by
seconds; without it (or if it is unreadable) batches are a fixed count of ids in sorted order.

SHARD="i/N" (0-based i) keeps one slice of the test ids so several CI jobs can each run a
slice; the slices together cover every test once. With durations the slices are balanced
by total seconds (longest first onto the least-loaded slice); without them a slice is
every Nth id of the sorted list (index % N == i).

`--record` writes each test's seconds to tests/durations.json after a passing run, merged
with what is there (ids that no longer exist are dropped). The file is never needed.

`--changed BASE` runs only the test modules that tests/affected.json maps the diff against BASE to, plus its safety set
(scripts/affected.py). It runs everything when it cannot tell, and prints one "mode:" line saying which and why.
SHARD still applies to whichever tests it picks.

A `--changed` run is a pull request run. It always runs the safety set and the "critical" list. It skips the tests tagged
"nightly" in tests/affected.json and the flaky ones listed in tests/quarantine.json, except when it falls back to
"mode: full": then it runs every test, nightly included, because a run that cannot tell what changed must not skip any.
Only the quarantined ones are still skipped. (The nightly run, which has no `--changed`, runs both.) And it has a time budget (docs/test-value.md): a test slower than 5s
in tests/durations.json fails the run unless it is critical (the safety set or the "critical" list), and so does a test with
no recorded time that takes over 15s in the run itself. The recorded file is the check because a loaded or different runner
cannot change it; the live time is only for a new test nobody has recorded yet, at a 3x margin.

Every run, pull request or not, prints the quarantine list so it cannot be forgotten. The list is never retried: a flaky
test is skipped in pull request runs and fails the suite itself (tests/test_quarantine.py) once its entry is 14 days old.

Fails closed: a failing batch fails the run, and so does any difference
between the number of tests found and the number that ran.
"""
import json
import math
import os
import queue
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import affected  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
DURATIONS = TESTS / "durations.json"
QUARANTINE = TESTS / "quarantine.json"
RAN = re.compile(r"^Ran (\d+) tests? in ([\d.]+)s", re.M)
TIMES = re.compile(r"^::durations:: (.*)$", re.M)
SECONDS = {}  # id -> seconds, filled by run() as batches finish
# A batch is at least this many seconds of work, so a process start (about 0.1s, plus a class fixture) stays a small part of it.
MIN_BATCH_SECS = 3.0
MAX_BATCH_IDS = 25
BUDGET_SECS = 5.0  # a pull request run takes no test slower than this unless it is critical
LIVE_MARGIN = 3  # ... and judges a test it has no record of at BUDGET_SECS x this, so a loaded runner does not fail it
QUARANTINE_DAYS = 14  # an entry older than this fails tests/test_quarantine.py
BATCHES_PER_WORKER = 8  # queue depth: enough small batches that the last ones even the workers out


def ids(suite):
    for t in suite:
        if isinstance(t, unittest.TestSuite):
            yield from ids(t)
        else:
            yield t.id()


def load_durations(path=DURATIONS):
    """{id: seconds} from the durations file. Never raises: a missing or unreadable file is {}, bad entries are dropped."""
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: float(v) for k, v in data.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0}


def estimate(found, durations):
    """{id: seconds} for every id in found; an id with no duration costs the median. None when no id has one."""
    known = [durations[t] for t in found if t in (durations or {})]
    if not known:
        return None
    med = statistics.median(known)
    return {t: durations.get(t, med) for t in found}


def select(found, spec, durations=None):
    """The ids a CI shard runs. spec is "i/N" with 0 <= i < N, or empty for all. Raises ValueError if malformed."""
    if not spec:
        return list(found)
    m = re.fullmatch(r"(\d+)/(\d+)", spec)
    if not m or not 0 <= int(m[1]) < int(m[2]):
        raise ValueError(f"SHARD must look like i/N with 0 <= i < N, got {spec!r}")
    i, n = int(m[1]), int(m[2])
    est = estimate(found, durations)
    if est is None:
        return [t for k, t in enumerate(sorted(found)) if k % n == i]
    loads = [0.0] * n
    mine = []
    for t in sorted(found, key=lambda t: (-est[t], t)):
        k = loads.index(min(loads))  # least loaded, lowest index on a tie
        loads[k] += est[t]
        if k == i:
            mine.append(t)
    return sorted(mine)


def batches(found, durations, workers):
    """The queue: a list of batches of ids, each id in exactly one. Longest-first when durations are known."""
    found = sorted(found)
    if not found:
        return []
    est = estimate(found, durations)
    if est is None:
        size = min(MAX_BATCH_IDS, max(1, math.ceil(len(found) / (workers * BATCHES_PER_WORKER))))
        return [found[i:i + size] for i in range(0, len(found), size)]
    target = max(MIN_BATCH_SECS, sum(est.values()) / (workers * BATCHES_PER_WORKER))
    out, cur, secs = [], [], 0.0
    for t in sorted(found, key=lambda t: (-est[t], t)):
        cur.append(t)
        secs += est[t]
        if secs >= target or len(cur) >= MAX_BATCH_IDS:
            out.append(cur)
            cur, secs = [], 0.0
    return out + ([cur] if cur else [])


def run(shard):
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(TESTS), os.environ.get("PYTHONPATH")]))}
    r = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "unit_batch.py"), *shard], cwd=ROOT, env=env,
                       capture_output=True, text=True)
    out = r.stdout + r.stderr
    t = TIMES.search(out)
    if t:
        try:
            SECONDS.update(json.loads(t[1]))
        except ValueError:
            pass
        out = TIMES.sub("", out).rstrip("\n") + "\n"
    m = RAN.search(out)
    return r.returncode, int(m.group(1)) if m else 0, float(m.group(2)) if m else 0.0, out


def run_queue(chunks, workers, runner=run):
    """Workers take the next batch from a shared queue until it is empty.

    Returns (one result per batch, [(tests run, seconds busy) per worker]). A batch whose runner raises is a failed
    batch with the error as its output, never a lost one.
    """
    q = queue.Queue()
    for c in chunks:
        q.put(c)
    results, stats, lock = [], [], threading.Lock()

    def work():
        n, busy = 0, 0.0
        while True:
            try:
                c = q.get_nowait()
            except queue.Empty:
                break
            t0 = time.perf_counter()
            try:
                r = runner(c)
            except Exception as e:  # noqa: BLE001 - any failure to run a batch must fail the run, not vanish
                r = (1, 0, 0.0, f"batch could not run: {e!r}\n  ids: {c[:5]}{' ...' if len(c) > 5 else ''}\n")
            busy += time.perf_counter() - t0
            n += r[1]
            with lock:
                results.append(r)
        with lock:
            stats.append((n, busy))

    threads = [threading.Thread(target=work) for _ in range(max(1, min(workers, len(chunks))))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results, stats


def only(found, entries):
    """The ids that an entry names. An entry is a module, test_x.Class or test_x.Class.test_y (ids look like the last)."""
    return [t for t in found if any(t == e or t.startswith(e + ".") for e in entries)]


def unmatched(found, entries):
    """The entries that name no test: a renamed class or test would otherwise drop out of the set unseen."""
    return [e for e in entries if not only(found, [e])]


def tiers(amap):
    """(critical entries, nightly entries) from the map. The safety set is critical too. Never raises: no tags is ([], [])."""
    amap = amap if isinstance(amap, dict) else {}
    pick = lambda k: [e for e in amap.get(k) if isinstance(e, str)] if isinstance(amap.get(k), list) else []  # noqa: E731
    return pick("safety") + pick("critical"), pick("nightly")


def over_budget(seconds, exempt, limit=BUDGET_SECS):
    """[(id, seconds)] slowest first, for each id in `seconds` ({id: seconds}) over the limit and not in `exempt`."""
    return sorted(((t, s) for t, s in seconds.items() if s > limit and t not in exempt), key=lambda x: -x[1])


def unrecorded_over_budget(seconds, durations, exempt):
    """The live half of the budget: [(id, seconds)] for tests with no recorded time that took over LIVE_MARGIN x BUDGET_SECS.
    A recorded test is never judged on its live time: a loaded or different runner would fail a test that is normally quick."""
    return over_budget({t: s for t, s in seconds.items() if t not in durations}, exempt, BUDGET_SECS * LIVE_MARGIN)


def load_quarantine(path=QUARANTINE):
    """The quarantine entries (dicts). A missing file is none. Raises ValueError when the file is not a list of objects."""
    try:
        data = json.loads(Path(path).read_text())
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as e:
        raise ValueError(f"{path} cannot be read: {e}") from e
    if not isinstance(data, list) or not all(isinstance(e, dict) for e in data):
        raise ValueError(f"{path} must be a list of objects")
    return data


def quarantine_problems(entries, found, today=None):
    """What is wrong with the quarantine list: a missing field, a bad or future date, a test that does not exist, a file
    that is not the test's own, or an entry older than QUARANTINE_DAYS. [] when it is fine."""
    today, out, seen = today or date.today(), [], set()
    for e in entries:
        t = e.get("test")
        miss = [k for k in ("test", "file", "reason", "date", "owner") if not isinstance(e.get(k), str) or not e[k].strip()]
        if miss:
            out.append(f"{t or e}: missing {', '.join(miss)}")
            continue
        if t in seen:
            out.append(f"{t}: listed twice")
        seen.add(t)
        if t not in found:
            out.append(f"{t}: no such test (renamed or deleted: remove the entry)")
        if e["file"] != f"tests/{t.split('.')[0]}.py":
            out.append(f"{t}: file should be tests/{t.split('.')[0]}.py")
        try:
            age = (today - date.fromisoformat(e["date"])).days
        except ValueError:
            out.append(f"{t}: date {e['date']!r} is not YYYY-MM-DD")
            continue
        if age < 0:
            out.append(f"{t}: dated in the future")
        elif age > QUARANTINE_DAYS:
            out.append(f"{t}: quarantined {age} days ago, over {QUARANTINE_DAYS}: fix it, or ask the owner before deleting it")
    return out


def quarantine_lines(entries, today=None):
    today = today or date.today()
    if not entries:
        return ["quarantine: none"]
    out = [f"quarantine: {len(entries)} flaky test(s), skipped in pull request runs, run nightly (fix within {QUARANTINE_DAYS} days):"]
    for e in entries:
        try:
            age = f"{(today - date.fromisoformat(e['date'])).days} days"
        except (KeyError, ValueError, TypeError):
            age = "unknown age"
        out.append(f"  {e.get('test')} | {age} | owner {e.get('owner')} | {e.get('reason')}")
    return out


def record(all_ids, path=DURATIONS):
    """Merge this run's seconds into the durations file, keeping only ids that still exist."""
    merged = {**load_durations(path), **SECONDS}
    keep = {t: merged[t] for t in sorted(all_ids) if t in merged}
    Path(path).write_text("{\n" + ",\n".join(f"{json.dumps(k)}: {v}" for k, v in keep.items()) + "\n}\n")
    return len(keep)


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
    all_ids = list(found)
    broken = [i for i in found if i.startswith("unittest.loader.")]
    if not found or broken:
        print(f"FAIL: {len(found)} tests found; import failures: {broken}")
        return 1
    pr = "--changed" in sys.argv
    full = False
    try:
        quarantined = load_quarantine()
    except ValueError as e:
        print(f"FAIL: {e}")
        return 1
    for line in quarantine_lines(quarantined):
        print(line)
    if pr:
        i = sys.argv.index("--changed")
        base = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
        mods, why = affected.plan(base)
        picked = only(found, mods) if mods is not None else []
        if mods is not None and (not picked or unmatched(found, mods)):
            mods, why = None, f"the map names tests that do not exist: {unmatched(found, mods)[:3] or 'all of them'}"
        print(f"mode: {'full' if mods is None else 'affected'} ({why})")
        full = mods is None
        if mods is not None:
            print(f"{len(picked)} of {len(found)} tests in {len({t.split('.')[0] for t in picked})} modules")
            found = picked
    durations = load_durations()
    try:
        always, nightly = tiers(json.loads(affected.MAP.read_text()))
    except (OSError, ValueError):
        always, nightly = [], []  # an unreadable map tags nothing
    exempt = set(only(all_ids, always))
    if pr and full:
        exempt |= set(only(all_ids, nightly))  # full mode runs nightly tests on purpose, so the budget lets them through
    if pr:
        skip = set() if full else set(only(found, nightly)) - exempt  # a test that is critical and nightly stays in
        skip_q = {e.get("test") for e in quarantined} & set(found)
        found = [t for t in found if t not in skip and t not in skip_q]
        print(f"skipped in this run: {len(skip)} nightly, {len(skip_q)} quarantined (the nightly run runs both)")
        slow = over_budget({t: durations[t] for t in found if t in durations}, exempt)
        if slow:
            print(f"FAIL: {len(slow)} test(s) in this run take over {BUDGET_SECS:.0f}s and are not critical. Tag each critical or "
                  "nightly in scripts/build_affected_map.py, or make it faster:")
            for t, secs in slow[:20]:
                print(f"  {secs:.0f}s {t}")
            return 1
    total = len(found)
    try:
        found = select(found, os.environ.get("SHARD", ""), durations)
    except ValueError as e:
        print(f"FAIL: {e}")
        return 1
    if os.environ.get("SHARD"):
        print(f"shard {os.environ['SHARD']}: {len(found)} of {total} tests")
    if not found:
        print("FAIL: this shard selected no tests")
        return 1
    workers = int(os.environ.get("TEST_WORKERS") or os.cpu_count() or 2)
    chunks = batches(found, durations, workers)
    results, per_worker = run_queue(chunks, workers)
    ran = sum(r[1] for r in results)
    bad = [r for r in results if r[0] != 0]
    for i, (n, busy) in enumerate(sorted(per_worker, key=lambda w: -w[1])):
        print(f"worker {i}: {n} tests, busy {busy:.1f}s")
    for code, _, _, out in bad:
        print(f"\n===== failing batch, exit {code} =====\n{out}")
    print(f"\n{ran} of {len(found)} tests ran in {len(chunks)} batches on {len(per_worker)} workers"
          f" ({'longest-first' if estimate(found, durations) else 'no durations'})")
    if ran != len(found):
        print("FAIL: tests found and tests run differ")
        return 1
    if pr:
        live = unrecorded_over_budget(SECONDS, durations, exempt)
        if live:
            print(f"FAIL: {len(live)} test(s) took over {BUDGET_SECS * LIVE_MARGIN:.0f}s in this run and are not critical "
                  "(run with --record, then tag each critical or nightly):")
            for t, secs in live[:20]:
                print(f"  {secs:.0f}s {t}")
            return 1
    if "--record" in sys.argv and not bad:
        print(f"recorded {record(all_ids)} durations in {DURATIONS.relative_to(ROOT)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
