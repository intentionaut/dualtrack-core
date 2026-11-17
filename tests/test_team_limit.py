"""Free covers 6 products in one state repo: a 7th new one stops setup, the 6 filed and any re-setup are untouched."""
import importlib.util
import pathlib
import sys
import unittest
try:
    import scratch
except ImportError:  # run as tests.test_x from the repo root
    from tests import scratch

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
spec = importlib.util.spec_from_file_location("setup_apply", KIT / "scripts/setup_apply.py")
setup_apply = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup_apply)


def state_with(n):
    home = pathlib.Path(scratch.mkdtemp()) / "dualtrack-state"
    for i in range(n):
        (home / f"p{i}").mkdir(parents=True)
        (home / f"p{i}" / "profile.md").write_text("# Product profile\n")
    home.mkdir(parents=True, exist_ok=True)
    return home


class TeamLimit(unittest.TestCase):
    def test_sixth_new_product_is_allowed(self):
        home = state_with(5)
        self.assertIsNone(setup_apply.team_limit(home, home / "new" / "profile.md"))

    def test_seventh_new_product_stops_and_changes_nothing(self):
        home = state_with(6)
        before = sorted(p.name for p in home.iterdir())
        with self.assertRaises(SystemExit) as e:
            setup_apply.team_limit(home, home / "new" / "profile.md")
        msg = str(e.exception)
        self.assertIn("Nothing was changed", msg)
        self.assertIn("utm_source=team-limit", msg)
        self.assertEqual(before, sorted(p.name for p in home.iterdir()))

    def test_re_setup_of_a_filed_product_is_never_blocked(self):
        home = state_with(8)
        self.assertIsNone(setup_apply.team_limit(home, home / "p3" / "profile.md"))

    def test_missing_state_folder_counts_as_empty(self):
        home = pathlib.Path(scratch.mkdtemp()) / "absent"
        self.assertIsNone(setup_apply.team_limit(home, home / "new" / "profile.md"))


if __name__ == "__main__":
    unittest.main()
