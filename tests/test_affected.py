"""The affected-test selector (INT-248): a PR runs the tests its changed files touch plus the safety set, and
anything it cannot place runs the whole suite."""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import affected  # noqa: E402
import test_parallel  # noqa: E402

AMAP = {
    "safety": ["test_sandbox_escape", "test_tamper"],
    "map": {"scripts/ghrest.py": ["test_ghrest"], "docs/*": [], "scripts/*.py": ["test_py39_syntax"]},
}
SAFETY = {"test_sandbox_escape", "test_tamper"}
REAL = json.loads((ROOT / "tests" / "affected.json").read_text())


class Choose(unittest.TestCase):
    def test_an_unmapped_file_runs_everything(self):
        mods, why = affected.choose(["scripts/ghrest.py", "brand_new_dir/x.txt"], AMAP)
        self.assertIsNone(mods)
        self.assertIn("brand_new_dir/x.txt", why)

    def test_a_daily_loop_change_runs_everything(self):
        amap = {**AMAP, "map": {**AMAP["map"], "scripts/daily_loop.sh": ["test_loop"]}}
        mods, why = affected.choose(["scripts/daily_loop.sh"], amap)
        self.assertIsNone(mods)
        self.assertIn("daily_loop.sh", why)

    def test_the_machinery_itself_runs_everything(self):
        for f in ("tests/affected.json", "scripts/affected.py", "scripts/test_parallel.py", ".github/workflows/test.yml",
                  ".github/workflows/anything-new.yml"):
            mods, _ = affected.choose([f], {"safety": ["test_a"], "map": {"*": ["test_x"]}})
            self.assertIsNone(mods, f)

    def test_a_mapped_file_runs_only_its_tests_plus_the_safety_set(self):
        mods, why = affected.choose(["scripts/ghrest.py"], AMAP)
        self.assertEqual(set(mods), SAFETY | {"test_ghrest", "test_py39_syntax"})
        self.assertIn("affected", why)

    def test_a_docs_only_change_runs_just_the_safety_set(self):
        mods, _ = affected.choose(["docs/notes.md", "docs/other.md"], AMAP)
        self.assertEqual(set(mods), SAFETY)

    def test_no_changed_files_runs_everything(self):
        self.assertIsNone(affected.choose([], AMAP)[0])

    def test_the_safety_set_is_never_dropped(self):
        for changed in (["docs/a.md"], ["scripts/ghrest.py"], ["scripts/ghrest.py", "docs/a.md"]):
            self.assertTrue(SAFETY <= set(affected.choose(changed, AMAP)[0]), changed)

    def test_the_critical_list_always_runs_like_the_safety_set(self):
        amap = {**AMAP, "critical": ["test_loop.Loop.test_a_red_branch_goes_back_to_the_engineer_before_any_review"]}
        for changed in (["docs/a.md"], ["scripts/ghrest.py"]):
            mods, _ = affected.choose(changed, amap)
            self.assertIn("test_loop.Loop.test_a_red_branch_goes_back_to_the_engineer_before_any_review", mods)
            self.assertTrue(SAFETY <= set(mods))

    def test_a_tag_list_that_is_not_a_list_runs_everything(self):
        for key in ("critical", "nightly"):
            self.assertIsNone(affected.choose(["docs/a.md"], {**AMAP, key: "test_x"})[0], key)

    def test_the_nightly_list_adds_nothing_to_a_pull_request_run(self):
        mods, _ = affected.choose(["docs/a.md"], {**AMAP, "nightly": ["test_slow.S.test_x"]})
        self.assertEqual(sorted(mods), sorted(SAFETY))

    def test_a_malformed_map_runs_everything(self):
        for bad in ({}, {"safety": [], "map": {}}, {"safety": "x", "map": {}}, None):
            self.assertIsNone(affected.choose(["docs/a.md"], bad)[0], bad)


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args], cwd=cwd, check=True,
                   capture_output=True)


class Plan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = pathlib.Path(self.tmp.name)
        git(self.repo, "init", "-q", "-b", "main")
        (self.repo / "docs").mkdir()
        (self.repo / "docs" / "a.md").write_text("a")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "base")
        git(self.repo, "checkout", "-q", "-b", "pr")

    def commit(self, rel, text="x"):
        p = self.repo / rel
        p.parent.mkdir(exist_ok=True)
        p.write_text(text)
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", rel)

    def test_a_missing_base_runs_everything(self):
        mods, why = affected.plan("no-such-ref", AMAP, self.repo)
        self.assertIsNone(mods)
        self.assertIn("base", why)

    def test_an_empty_base_runs_everything(self):
        self.assertIsNone(affected.plan("", AMAP, self.repo)[0])

    def test_a_docs_change_in_a_real_repo_runs_the_safety_set(self):
        self.commit("docs/b.md")
        mods, _ = affected.plan("main", AMAP, self.repo)
        self.assertEqual(set(mods), SAFETY)

    def test_a_renamed_file_counts_under_both_names(self):
        git(self.repo, "mv", "docs/a.md", "elsewhere.md")
        git(self.repo, "commit", "-q", "-m", "mv")
        mods, why = affected.plan("main", AMAP, self.repo)
        self.assertIsNone(mods)
        self.assertIn("elsewhere.md", why)

    def test_a_directory_that_is_not_a_repo_runs_everything(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(affected.plan("main", AMAP, pathlib.Path(d))[0])


class RealMap(unittest.TestCase):
    def named(self):
        # a safety entry is a module, test_x.Class or test_x.Class.test_y: its module is reachable
        return {e.split(".")[0] for e in REAL["safety"]} | {m for mods in REAL["map"].values() for m in mods}

    def test_every_test_module_is_reachable_from_the_map_or_the_safety_set(self):
        on_disk = {p.stem for p in (ROOT / "tests").glob("test_*.py")}
        self.assertEqual(sorted(on_disk - self.named()), [],
                         "a test no PR would ever run: regenerate tests/affected.json with scripts/build_affected_map.py")

    def test_the_map_names_only_real_test_modules(self):
        on_disk = {p.stem for p in (ROOT / "tests").glob("test_*.py")}
        self.assertEqual(sorted(self.named() - on_disk), [])

    def test_the_safety_set_covers_the_named_areas(self):
        for m in ("test_sandbox_escape", "test_tamper", "test_merge_gate", "test_egress", "test_delayed_exfil",
                  "test_encoded_exfil"):
            self.assertIn(m, REAL["safety"])

    def test_the_safety_set_reaches_into_the_big_modules_for_canary_lock_and_sandbox_tests(self):
        for prefix in ("test_loop.", "test_setup.OfflineBox", "test_setup.NestedSandbox", "test_handoff.", "test_mcp_server."):
            self.assertTrue(any(e.startswith(prefix) for e in REAL["safety"]), prefix)
        self.assertTrue(any("canary" in e for e in REAL["safety"]))
        self.assertTrue(any("lock" in e.split(".")[-1].split("_") for e in REAL["safety"]))
        self.assertNotIn("test_loop", REAL["safety"], "the whole of test_loop in the safety set erases the saving")

    def ids(self):
        import unittest
        suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT / "tests"))
        return list(test_parallel.ids(suite))

    def test_every_test_over_five_seconds_is_critical_or_nightly(self):
        # The recorded half of the time budget, checked on every run: a slow test must be tagged, wherever it lives.
        always, nightly = test_parallel.tiers(REAL)
        tagged = set(test_parallel.only(self.ids(), always + nightly))
        slow = {t: s for t, s in test_parallel.load_durations().items() if s > test_parallel.BUDGET_SECS}
        slow = {t: s for t, s in slow.items() if t in set(self.ids())}
        self.assertEqual(sorted(set(slow) - tagged), [],
                         "tag each in scripts/build_affected_map.py (CRITICAL or NIGHTLY), run it, and commit tests/affected.json")

    def test_no_test_is_both_critical_and_nightly(self):
        always, nightly = test_parallel.tiers(REAL)
        found = self.ids()
        self.assertEqual(sorted(set(test_parallel.only(found, always)) & set(test_parallel.only(found, nightly))), [])

    def test_every_tag_names_a_real_test(self):
        found = self.ids()
        for key in ("critical", "nightly"):
            self.assertEqual(test_parallel.unmatched(found, REAL[key]), [], key)

    def test_the_selector_tests_always_run(self):
        self.assertIn("test_affected", REAL["safety"])

    def test_a_safety_file_is_mapped_to_its_test(self):
        mods, _ = affected.choose(["scripts/tamper.py"], REAL)
        self.assertIn("test_tamper", mods)

    def test_the_committed_map_is_what_the_generator_makes(self):
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_affected_map.py"), "--check"], cwd=ROOT,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class Only(unittest.TestCase):
    def test_only_keeps_the_ids_of_the_named_modules(self):
        ids = ["test_a.A.test_1", "test_a.B.test_2", "test_b.A.test_1", "test_ab.A.test_1"]
        self.assertEqual(test_parallel.only(ids, {"test_a"}), ["test_a.A.test_1", "test_a.B.test_2"])
        self.assertEqual(test_parallel.only(ids, set()), [])

    def test_only_matches_a_class_or_one_test_by_id_prefix(self):
        ids = ["test_a.A.test_1", "test_a.A.test_2", "test_a.B.test_1", "test_ab.A.test_1"]
        self.assertEqual(test_parallel.only(ids, {"test_a.A"}), ["test_a.A.test_1", "test_a.A.test_2"])
        self.assertEqual(test_parallel.only(ids, {"test_a.B.test_1"}), ["test_a.B.test_1"])
        self.assertEqual(test_parallel.only(ids, {"test_a.A.test"}), [])

    def test_an_entry_that_matches_no_test_is_reported(self):
        ids = ["test_a.A.test_1", "test_b.A.test_1"]
        self.assertEqual(test_parallel.unmatched(ids, ["test_a", "test_a.Gone", "test_c.A.test_1"]), ["test_a.Gone", "test_c.A.test_1"])


class Cli(unittest.TestCase):
    def test_a_missing_base_prints_one_full_mode_line(self):
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "affected.py"), "no-such-ref"], cwd=ROOT,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertTrue(r.stdout.startswith("mode: full"), r.stdout)


if __name__ == "__main__":
    unittest.main()
