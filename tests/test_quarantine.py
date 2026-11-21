"""The flaky-test quarantine (INT-248): tests/quarantine.json lists each flaky test with its file, reason, date and owner.
A listed test is skipped in pull request runs and runs nightly; every run prints the list; an entry over 14 days old
fails the suite here. Nothing retries a test."""
import json
import pathlib
import sys
import tempfile
import unittest
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import test_parallel  # noqa: E402

TODAY = date(2026, 11, 21)
IDS = ["test_a.A.test_x", "test_a.A.test_y", "test_b.B.test_z"]


def entry(**kw):
    return {"test": "test_a.A.test_x", "file": "tests/test_a.py", "reason": "fails 1 run in 20 on a loaded runner",
            "date": "2026-11-15", "owner": "engineering", **kw}


class Problems(unittest.TestCase):
    def problems(self, *entries):
        return test_parallel.quarantine_problems(list(entries), IDS, TODAY)

    def test_a_complete_recent_entry_is_fine(self):
        self.assertEqual(self.problems(entry()), [])

    def test_an_empty_list_is_fine(self):
        self.assertEqual(self.problems(), [])

    def test_an_entry_exactly_14_days_old_is_fine_and_15_fails(self):
        self.assertEqual(self.problems(entry(date="2026-11-07")), [])
        self.assertIn("quarantined 15 days ago", self.problems(entry(date="2026-11-06"))[0])

    def test_each_missing_field_is_named(self):
        for k in ("test", "file", "reason", "date", "owner"):
            e = entry()
            del e[k]
            self.assertIn(f"missing {k}", self.problems(e)[0], k)
        self.assertIn("missing reason", self.problems(entry(reason="  "))[0])

    def test_a_test_that_no_longer_exists_is_named_so_a_rename_cannot_hide_it(self):
        self.assertIn("no such test", self.problems(entry(test="test_a.A.test_gone"))[0])

    def test_the_file_must_be_the_tests_own(self):
        self.assertIn("file should be tests/test_a.py", self.problems(entry(file="tests/test_b.py"))[0])

    def test_a_bad_or_future_date_is_a_problem(self):
        self.assertIn("not YYYY-MM-DD", self.problems(entry(date="last week"))[0])
        self.assertIn("future", self.problems(entry(date="2026-12-01"))[0])

    def test_a_test_listed_twice_is_a_problem(self):
        self.assertIn("listed twice", " ".join(self.problems(entry(), entry())))


class Lines(unittest.TestCase):
    def test_an_empty_list_still_prints_a_line(self):
        self.assertEqual(test_parallel.quarantine_lines([], TODAY), ["quarantine: none"])

    def test_every_entry_is_printed_with_its_age_owner_and_reason(self):
        out = "\n".join(test_parallel.quarantine_lines([entry()], TODAY))
        for part in ("1 flaky test", "test_a.A.test_x", "6 days", "owner engineering", "fails 1 run in 20"):
            self.assertIn(part, out)


class Loading(unittest.TestCase):
    def load(self, text):
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / "q.json"
            if text is not None:
                f.write_text(text)
            return test_parallel.load_quarantine(f)

    def test_a_missing_file_is_no_quarantine(self):
        self.assertEqual(self.load(None), [])

    def test_a_malformed_file_is_an_error_not_an_empty_list(self):
        for text in ("{ nope", "{}", '["a"]'):
            with self.assertRaises(ValueError, msg=text):
                self.load(text)


class Real(unittest.TestCase):
    """The committed list. This is the test that fails when an entry is older than 14 days."""

    def test_no_entry_is_older_than_14_days_and_every_entry_is_whole(self):
        import unittest as u
        suite = u.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT / "tests"))
        entries = test_parallel.load_quarantine(ROOT / "tests" / "quarantine.json")
        self.assertEqual(test_parallel.quarantine_problems(entries, set(test_parallel.ids(suite))), [])

    def test_the_committed_file_is_a_list(self):
        self.assertIsInstance(json.loads((ROOT / "tests" / "quarantine.json").read_text()), list)


if __name__ == "__main__":
    unittest.main()
