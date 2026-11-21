"""The owner can find the dashboard: front door command, setup pointer, README."""
import unittest
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
DOOR = (KIT / "skills/dualtrack/SKILL.md").read_text()
SETUP = (KIT / "skills/dualtrack-setup/SKILL.md").read_text()
README = (KIT / "README.md").read_text()


class DashboardCommand(unittest.TestCase):
    def test_front_door_routes_dashboard_to_server_with_fallbacks(self):
        sec = DOOR.split("## Open the dashboard", 1)[1].split("\n## ", 1)[0]
        for phrase in ("/dualtrack dashboard", "show my dashboard", "open the dashboard"):
            self.assertIn(phrase, sec)
        self.assertIn("python3 <kit>/scripts/dashboard_server.py", sec)
        self.assertIn("open <context>/dashboard.html", sec)
        self.assertIn("xdg-open", sec)
        self.assertIn("appears after the first run", sec)

    def test_first_run_check_comes_before_the_server_which_runs_in_the_background(self):
        # The server renders live and never reads dashboard.html, so checking after launching it never fires.
        sec = DOOR.split("## Open the dashboard", 1)[1].split("\n## ", 1)[0]
        self.assertLess(sec.index("appears after the first run"), sec.index("dashboard_server.py"))
        self.assertIn("in the background", sec)

    def test_decisions_state_still_offers_dashboard(self):
        row = next(l for l in DOOR.splitlines() if l.startswith("| `decisions`"))
        self.assertIn("offer the dashboard", row)

    def test_setup_ends_with_one_dashboard_line(self):
        tail = SETUP.split("## 6. Then", 1)[1]
        bullets = [l for l in tail.splitlines() if l.startswith("- ")]
        self.assertIn("dashboard", bullets[-1])
        self.assertIn("/dualtrack dashboard", bullets[-1])
        self.assertEqual(len([l for l in tail.splitlines() if "dashboard" in l]), 1)

    def test_readme_lists_command(self):
        self.assertRegex(README, r"`/dualtrack dashboard`")
        self.assertIn("`scripts/dashboard_server.py`", README)  # existing rows kept


if __name__ == "__main__":
    unittest.main()
