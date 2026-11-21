"""test_parallel.py: the work queue, the durations file and balanced CI shards (INT-248)."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import test_parallel  # noqa: E402

IDS = [f"test_m{m}.C{c}.test_{i}" for m in range(3) for c in range(2) for i in range(9)]
DUR = {t: float((k * 7) % 13 + 1) for k, t in enumerate(IDS)}


def flat(chunks):
    return [t for c in chunks for t in c]


class Durations(unittest.TestCase):
    def load(self, text):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "durations.json"
            if text is not None:
                p.write_text(text)
            return test_parallel.load_durations(p)

    def test_a_missing_file_is_no_durations(self):
        self.assertEqual(self.load(None), {})

    def test_a_malformed_file_is_no_durations(self):
        for bad in ("", "{", "[1, 2]", '"x"', "null", "\x00\xff"):
            self.assertEqual(self.load(bad), {}, repr(bad))

    def test_bad_entries_are_dropped_and_good_ones_kept(self):
        got = self.load(json.dumps({"a.B.c": 1.5, "a.B.d": "slow", "a.B.e": -1, "a.B.f": True, "a.B.g": None, "a.B.h": 0}))
        self.assertEqual(got, {"a.B.c": 1.5, "a.B.h": 0.0})

    def test_a_missing_id_costs_the_median(self):
        est = test_parallel.estimate(["a", "b", "c", "new"], {"a": 1.0, "b": 3.0, "c": 9.0})
        self.assertEqual(est["new"], 3.0)
        self.assertEqual(est["c"], 9.0)

    def test_no_known_duration_means_no_estimate(self):
        self.assertIsNone(test_parallel.estimate(["a", "b"], {}))
        self.assertIsNone(test_parallel.estimate(["a", "b"], {"zzz": 4.0}))


class BalancedShards(unittest.TestCase):
    def test_every_id_lands_in_exactly_one_shard(self):
        for n in (1, 2, 3, 4, 7, 60):
            got = [t for i in range(n) for t in test_parallel.select(IDS, f"{i}/{n}", DUR)]
            self.assertEqual(sorted(got), sorted(IDS), n)

    def test_ids_with_no_duration_are_still_covered_once(self):
        part = {t: d for t, d in DUR.items() if not t.startswith("test_m2")}
        got = [t for i in range(4) for t in test_parallel.select(IDS, f"{i}/4", part)]
        self.assertEqual(sorted(got), sorted(IDS))

    def test_the_split_is_deterministic(self):
        a = [test_parallel.select(IDS, f"{i}/4", DUR) for i in range(4)]
        b = [test_parallel.select(IDS[::-1], f"{i}/4", dict(reversed(list(DUR.items())))) for i in range(4)]
        self.assertEqual(a, b)

    def test_shards_are_balanced_by_time_not_count(self):
        loads = [sum(DUR[t] for t in test_parallel.select(IDS, f"{i}/4", DUR)) for i in range(4)]
        rr = [sum(DUR[t] for t in sorted(IDS)[i::4]) for i in range(4)]
        self.assertLessEqual(max(loads) - min(loads), max(DUR.values()))
        self.assertLessEqual(max(loads) - min(loads), max(rr) - min(rr))

    def test_one_huge_test_gets_a_shard_to_itself(self):
        dur = {**{t: 1.0 for t in IDS}, IDS[5]: 500.0}
        loads = {i: test_parallel.select(IDS, f"{i}/4", dur) for i in range(4)}
        self.assertTrue(any(v == [IDS[5]] for v in loads.values()))

    def test_without_durations_the_split_is_todays_round_robin(self):
        for spec in ("0/4", "3/4"):
            self.assertEqual(test_parallel.select(IDS, spec, {}), test_parallel.select(IDS, spec))
            self.assertEqual(test_parallel.select(IDS, spec, None), sorted(IDS)[int(spec[0])::4])

    def test_a_malformed_spec_still_raises(self):
        for bad in ("x", "4/4", "1/0"):
            with self.assertRaises(ValueError):
                test_parallel.select(IDS, bad, DUR)


class Batches(unittest.TestCase):
    def test_every_id_is_in_exactly_one_batch(self):
        for dur in (DUR, {}, {IDS[0]: 3.0}):
            for workers in (1, 2, 5, 64):
                got = flat(test_parallel.batches(IDS, dur, workers))
                self.assertEqual(sorted(got), sorted(IDS), (bool(dur), workers))

    def test_batches_are_small_and_never_empty(self):
        out = test_parallel.batches(IDS, {}, 4)
        self.assertTrue(all(out))
        self.assertGreater(len(out), 4)

    def test_with_durations_the_longest_work_goes_first(self):
        out = test_parallel.batches(IDS, DUR, 4)
        first = [DUR[t] for t in out[0]]
        self.assertEqual(max(first), max(DUR.values()))
        firsts = [max(DUR[t] for t in b) for b in out]
        self.assertEqual(firsts, sorted(firsts, reverse=True))

    def test_the_order_is_deterministic(self):
        self.assertEqual(test_parallel.batches(IDS, DUR, 4), test_parallel.batches(IDS[::-1], DUR, 4))
        self.assertEqual(test_parallel.batches(IDS, {}, 4), test_parallel.batches(IDS[::-1], {}, 4))

    def test_no_ids_no_batches(self):
        self.assertEqual(test_parallel.batches([], DUR, 4), [])


class Queue(unittest.TestCase):
    def fake(self, shard):
        return 0, len(shard), 0.0, ""

    def test_every_batch_runs_once_whatever_the_worker_count(self):
        chunks = test_parallel.batches(IDS, DUR, 4)
        for workers in (1, 3, 8):
            seen = []

            def run(b):
                seen.append(tuple(b))
                return 0, len(b), 0.01, ""
            results, per_worker = test_parallel.run_queue(chunks, workers, run)
            self.assertEqual(sorted(flat(map(list, seen))), sorted(IDS))
            self.assertEqual(sum(r[1] for r in results), len(IDS))
            self.assertEqual(sum(n for n, _ in per_worker), len(IDS))
            self.assertLessEqual(len(per_worker), workers)

    def test_a_crash_in_the_runner_is_a_failed_batch_not_a_lost_one(self):
        def run(b):
            if "boom" in b:
                raise OSError("cannot start")
            return 0, len(b), 0.0, ""
        results, _ = test_parallel.run_queue([["a"], ["boom"], ["c"]], 2, run)
        self.assertEqual(len(results), 3)
        bad = [r for r in results if r[0] != 0]
        self.assertEqual(len(bad), 1)
        self.assertIn("cannot start", bad[0][3])


def clean_env(**extra):
    """The environment without the knobs CI sets for the real run (SHARD, TEST_WORKERS), which would reshape a throwaway one."""
    env = {k: v for k, v in os.environ.items() if k not in ("SHARD", "TEST_WORKERS")}
    return {**env, **extra}


class Subprocess(unittest.TestCase):
    """The real thing, against a throwaway tests folder: a failing batch fails the run and shows its output."""

    def make(self, d, body):
        t = pathlib.Path(d) / "tests"
        t.mkdir()
        (t / "test_tmp_a.py").write_text("import unittest\nclass A(unittest.TestCase):\n    def test_ok(self): pass\n"
                                         "    def test_ok2(self): pass\n" + body)
        return t

    def run_in(self, body, *args, env=None):
        with tempfile.TemporaryDirectory() as d:
            self.make(d, body)
            # a copy of the runner pointed at the throwaway folder
            scripts = pathlib.Path(d) / "scripts"
            scripts.mkdir()
            for name in ("test_parallel.py", "affected.py", "unit_batch.py"):
                (scripts / name).write_text((ROOT / "scripts" / name).read_text())
            return subprocess.run([sys.executable, str(scripts / "test_parallel.py"), *args], cwd=d, capture_output=True,
                                  text=True, env=clean_env(TEST_WORKERS="2", **(env or {})))

    def test_a_passing_suite_passes_and_counts_every_test(self):
        r = self.run_in("")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("2 of 2 tests ran", r.stdout)

    def test_a_failing_test_fails_the_run_and_shows_its_output(self):
        r = self.run_in("    def test_bad(self): self.fail('the reason shown')\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("the reason shown", r.stdout)

    def test_the_repo_root_is_importable_in_a_batch_as_under_python_m_unittest(self):
        r = self.run_in("    def test_root(self):\n        import tests\n        self.assertTrue(tests.__path__)\n")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("3 of 3 tests ran", r.stdout)

    def test_a_batch_that_dies_hard_fails_the_run(self):
        r = self.run_in("    def test_die(self):\n        import os\n        os._exit(3)\n")
        self.assertNotEqual(r.returncode, 0)

    def test_the_ci_shard_variables_do_not_leak_into_these_runs(self):
        old = os.environ.get("SHARD")
        os.environ["SHARD"] = "0/4"
        self.addCleanup(lambda: os.environ.pop("SHARD") if old is None else os.environ.update(SHARD=old))
        r = self.run_in("")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("2 of 2 tests ran", r.stdout)

    def test_a_malformed_durations_file_changes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            self.make(d, "")
            (pathlib.Path(d) / "tests" / "durations.json").write_text("{ not json")
            scripts = pathlib.Path(d) / "scripts"
            scripts.mkdir()
            for name in ("test_parallel.py", "affected.py", "unit_batch.py"):
                (scripts / name).write_text((ROOT / "scripts" / name).read_text())
            r = subprocess.run([sys.executable, str(scripts / "test_parallel.py")], cwd=d, capture_output=True, text=True,
                               env=clean_env())
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("2 of 2 tests ran", r.stdout)

    def test_record_writes_a_duration_for_every_test_that_ran(self):
        with tempfile.TemporaryDirectory() as d:
            self.make(d, "")
            scripts = pathlib.Path(d) / "scripts"
            scripts.mkdir()
            for name in ("test_parallel.py", "affected.py", "unit_batch.py"):
                (scripts / name).write_text((ROOT / "scripts" / name).read_text())
            r = subprocess.run([sys.executable, str(scripts / "test_parallel.py"), "--record"], cwd=d, capture_output=True,
                               text=True, env=clean_env(TEST_WORKERS="2"))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            got = json.loads((pathlib.Path(d) / "tests" / "durations.json").read_text())
            self.assertEqual(sorted(got), ["test_tmp_a.A.test_ok", "test_tmp_a.A.test_ok2"])
            self.assertTrue(all(isinstance(v, (int, float)) and v >= 0 for v in got.values()))


class Budget(unittest.TestCase):
    """A pull request run takes no test slower than 5s unless it is critical (INT-248)."""

    def test_a_slow_test_that_is_not_exempt_is_over_budget_slowest_first(self):
        self.assertEqual(test_parallel.over_budget({"a": 5.1, "b": 9.0, "c": 4.9, "d": 30.0}, {"d"}), [("b", 9.0), ("a", 5.1)])

    def test_exactly_the_limit_is_in_budget(self):
        self.assertEqual(test_parallel.over_budget({"a": 5.0}, set()), [])

    def test_the_live_margin_is_three_times_the_budget(self):
        live = test_parallel.BUDGET_SECS * test_parallel.LIVE_MARGIN
        self.assertEqual(test_parallel.over_budget({"a": live, "b": live + 0.1}, set(), live), [("b", live + 0.1)])

    def test_a_recorded_test_is_never_judged_on_its_live_time(self):
        # 3s on record, 40s today on a loaded or different runner: the record decides, so it passes.
        live = {"rec": 40.0, "new_ok": 14.9, "new_slow": 16.0, "new_crit": 90.0}
        got = test_parallel.unrecorded_over_budget(live, {"rec": 3.0}, {"new_crit"})
        self.assertEqual(got, [("new_slow", 16.0)])

    def test_the_safety_set_and_the_critical_list_are_both_critical(self):
        crit, night = test_parallel.tiers({"safety": ["test_a"], "critical": ["test_b.C"], "nightly": ["test_c.D.test_e"], "map": {}})
        self.assertEqual((crit, night), (["test_a", "test_b.C"], ["test_c.D.test_e"]))

    def test_a_map_with_no_tags_or_junk_tags_tags_nothing(self):
        self.assertEqual(test_parallel.tiers({}), ([], []))
        self.assertEqual(test_parallel.tiers(None), ([], []))
        self.assertEqual(test_parallel.tiers({"safety": None, "critical": [1, "x"], "nightly": "oops"}), (["x"], []))


class PullRequestRun(unittest.TestCase):
    """The real runner in a throwaway git repo: a change to docs/x.md against its parent, as `--changed HEAD~1`."""

    TESTS = ("import unittest\nclass A(unittest.TestCase):\n    def test_fast(self): pass\n"
             "    def test_slow_critical(self): pass\n    def test_slow_untagged(self): pass\n"
             "    def test_slow_nightly(self): pass\n    def test_flaky(self): pass\n")

    def git(self, d, *a):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t.invalid", *a], cwd=d, check=True, capture_output=True)

    def repo(self, d, durations=None, amap=None, quarantine=None):
        d = pathlib.Path(d)
        (d / "tests").mkdir()
        (d / "scripts").mkdir()
        (d / "docs").mkdir()
        (d / "tests" / "test_tmp_a.py").write_text(self.TESTS)
        base = {"safety": ["test_tmp_a.A.test_fast", "test_tmp_a.A.test_slow_critical"], "critical": [], "nightly": [],
                "map": {"docs/*": ["test_tmp_a.A.test_slow_untagged"]}}
        (d / "tests" / "affected.json").write_text(json.dumps({**base, **(amap or {})}))
        (d / "tests" / "durations.json").write_text(json.dumps(durations or {}))
        if quarantine is not None:
            (d / "tests" / "quarantine.json").write_text(json.dumps(quarantine))
        for name in ("test_parallel.py", "affected.py", "unit_batch.py"):
            (d / "scripts" / name).write_text((ROOT / "scripts" / name).read_text())
        (d / "docs" / "x.md").write_text("one\n")
        self.git(d, "init", "-q", "-b", "main")
        self.git(d, "add", ".")
        self.git(d, "commit", "-qm", "base")
        (d / "docs" / "x.md").write_text("two\n")
        self.git(d, "commit", "-qam", "docs change")
        return d

    def run_in(self, d, *args):
        return subprocess.run([sys.executable, str(d / "scripts" / "test_parallel.py"), *args], cwd=d, capture_output=True,
                              text=True, env=clean_env(TEST_WORKERS="2"))

    def test_an_untagged_test_over_five_seconds_fails_a_pull_request_run_and_names_it(self):
        with tempfile.TemporaryDirectory() as d:
            d = self.repo(d, {"test_tmp_a.A.test_slow_untagged": 6.0})
            r = self.run_in(d, "--changed", "HEAD~1")
            self.assertNotEqual(r.returncode, 0, r.stdout)
            self.assertIn("take over 5s and are not critical", r.stdout)
            self.assertIn("6s test_tmp_a.A.test_slow_untagged", r.stdout)
            self.assertNotIn("tests ran", r.stdout, "it fails before running anything")

    def test_a_critical_test_over_five_seconds_is_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            d = self.repo(d, {"test_tmp_a.A.test_slow_critical": 40.0, "test_tmp_a.A.test_fast": 0.1})
            r = self.run_in(d, "--changed", "HEAD~1")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("3 of 3 tests ran", r.stdout)

    def test_the_same_slow_test_is_fine_outside_a_pull_request_run(self):
        with tempfile.TemporaryDirectory() as d:
            d = self.repo(d, {"test_tmp_a.A.test_slow_untagged": 60.0})
            r = self.run_in(d)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("5 of 5 tests ran", r.stdout)

    def test_nightly_tests_are_skipped_in_a_pull_request_run_and_run_in_the_nightly_run(self):
        amap = {"nightly": ["test_tmp_a.A.test_slow_nightly", "test_tmp_a.A.test_slow_untagged"],
                "map": {"docs/*": ["test_tmp_a"]}}
        with tempfile.TemporaryDirectory() as d:
            d = self.repo(d, {"test_tmp_a.A.test_slow_nightly": 50.0}, amap)
            pr = self.run_in(d, "--changed", "HEAD~1")
            self.assertEqual(pr.returncode, 0, pr.stdout + pr.stderr)
            self.assertIn("skipped in this run: 2 nightly", pr.stdout)
            self.assertIn("3 of 3 tests ran", pr.stdout)
            full = self.run_in(d)
            self.assertEqual(full.returncode, 0, full.stdout + full.stderr)
            self.assertIn("5 of 5 tests ran", full.stdout, "the nightly run still runs every test")
            self.assertNotIn("skipped in this run", full.stdout)

    def test_a_pull_request_run_that_falls_back_to_everything_runs_the_nightly_tests_too(self):
        amap = {"nightly": ["test_tmp_a.A.test_slow_nightly"], "map": {"docs/*": ["test_tmp_a"]}}
        with tempfile.TemporaryDirectory() as d:
            d = self.repo(d, {"test_tmp_a.A.test_slow_nightly": 50.0}, amap)
            (d / "unmapped.txt").write_text("x")
            self.git(d, "add", ".")
            self.git(d, "commit", "-qm", "unmapped")
            r = self.run_in(d, "--changed", "HEAD~1")
            self.assertIn("mode: full", r.stdout)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("skipped in this run: 0 nightly", r.stdout)
            self.assertIn("5 of 5 tests ran", r.stdout, "a run that cannot tell what changed runs the slow nightly test too")

    def test_a_full_mode_pull_request_run_still_skips_quarantined_tests(self):
        with tempfile.TemporaryDirectory() as d:
            d = self.repo(d, {}, {"map": {"docs/*": ["test_tmp_a"]}}, self.QUARANTINE)
            (d / "unmapped.txt").write_text("x")
            self.git(d, "add", ".")
            self.git(d, "commit", "-qm", "unmapped")
            r = self.run_in(d, "--changed", "HEAD~1")
            self.assertIn("mode: full", r.stdout)
            self.assertIn("4 of 4 tests ran", r.stdout)

    def test_a_test_that_is_critical_and_nightly_stays_in(self):
        amap = {"nightly": ["test_tmp_a.A.test_slow_critical"], "map": {"docs/*": []}}
        with tempfile.TemporaryDirectory() as d:
            d = self.repo(d, {}, amap)
            r = self.run_in(d, "--changed", "HEAD~1")
            self.assertIn("skipped in this run: 0 nightly", r.stdout)
            self.assertIn("2 of 2 tests ran", r.stdout)

    QUARANTINE = [{"test": "test_tmp_a.A.test_flaky", "file": "tests/test_tmp_a.py", "reason": "flaky on a loaded runner",
                   "date": "2026-11-20", "owner": "engineering"}]

    def test_a_quarantined_test_is_skipped_in_a_pull_request_run_and_runs_nightly_and_the_list_is_printed_both_times(self):
        amap = {"map": {"docs/*": ["test_tmp_a"]}}
        with tempfile.TemporaryDirectory() as d:
            d = self.repo(d, {}, amap, self.QUARANTINE)
            pr = self.run_in(d, "--changed", "HEAD~1")
            self.assertEqual(pr.returncode, 0, pr.stdout + pr.stderr)
            self.assertIn("skipped in this run: 0 nightly, 1 quarantined", pr.stdout)
            self.assertIn("4 of 4 tests ran", pr.stdout)
            full = self.run_in(d)
            self.assertEqual(full.returncode, 0, full.stdout + full.stderr)
            self.assertIn("5 of 5 tests ran", full.stdout, "the nightly run still runs the flaky test")
            for out in (pr.stdout, full.stdout):
                self.assertIn("quarantine: 1 flaky test(s)", out)
                self.assertIn("test_tmp_a.A.test_flaky | ", out)
                self.assertIn("owner engineering", out)

    def test_a_run_with_no_quarantine_says_so(self):
        with tempfile.TemporaryDirectory() as d:
            d = self.repo(d, {}, None, [])
            self.assertIn("quarantine: none", self.run_in(d).stdout)

    def test_a_malformed_quarantine_file_fails_the_run(self):
        with tempfile.TemporaryDirectory() as d:
            d = self.repo(d, {}, None, [])
            (d / "tests" / "quarantine.json").write_text("{ nope")
            r = self.run_in(d)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("cannot be read", r.stdout)

    def test_a_test_with_no_recorded_time_passes_the_recorded_check(self):
        with tempfile.TemporaryDirectory() as d:
            d = self.repo(d, {})
            r = self.run_in(d, "--changed", "HEAD~1")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
