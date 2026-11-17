"""portfolio.py: one row per product in a state repo, read from the record alone."""
import json
import pathlib
import subprocess
import sys
import unittest
try:
    import scratch
except ImportError:  # run as tests.test_x from the repo root
    from tests import scratch

KIT = pathlib.Path(__file__).resolve().parent.parent


class Portfolio(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(scratch.mkdtemp())
        self.state = self.root / "dualtrack-state"
        for name, log, bets, options in (
                ("shop", "- 2026-11-03 | opened: Add a button, https://x/pull/1 | $2.10\n",
                 "- 2026-11-03 | Fix checkout copy | confirmed by owner\n",
                 {"date": "2026-11-04", "options": [{"change": "a"}, {"change": "b"}], "question": "How many calls?"}),
                ("blog", "", "", {})):
            ctx = self.state / name / "product-context"; ctx.mkdir(parents=True)
            (self.state / name / "profile.md").write_text(f"**Context path:** ../dualtrack-state/{name}/product-context\n")
            (ctx / "team-log.md").write_text("# Team log\n\n" + log)
            (ctx / "bets.md").write_text(bets)
            if options:
                (ctx / "options.json").write_text(json.dumps(options))

    def run_portfolio(self):
        return subprocess.run([sys.executable, str(KIT / "scripts/portfolio.py"), str(self.state)],
                              capture_output=True, text=True)

    def test_one_row_per_product_from_the_record(self):
        r = self.run_portfolio()
        self.assertEqual(r.returncode, 0, r.stderr)
        rows = [l for l in r.stdout.splitlines() if l.startswith("| ") and "---" not in l][1:]
        self.assertEqual(len(rows), 2)
        blog, shop = rows
        self.assertIn("| blog | no run yet | none | none | none |", blog)
        self.assertIn("2026-11-03: opened: Add a button", shop)
        self.assertIn("Fix checkout copy", shop)
        self.assertIn("2 from 2026-11-04", shop)
        self.assertIn("How many calls?", shop)

    def test_changes_nothing(self):
        before = sorted((p, p.read_bytes()) for p in self.state.rglob("*") if p.is_file())
        self.run_portfolio()
        self.assertEqual(before, sorted((p, p.read_bytes()) for p in self.state.rglob("*") if p.is_file()))

    def test_empty_state_repo_says_what_it_needs(self):
        empty = self.root / "empty"; empty.mkdir()
        r = subprocess.run([sys.executable, str(KIT / "scripts/portfolio.py"), str(empty)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 3)
        self.assertIn("profile.md", r.stdout)


if __name__ == "__main__":
    unittest.main()
