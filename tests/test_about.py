"""The bug-report helper prints the kit version and the system, and nothing private."""
import json
import pathlib
import sys
import unittest

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
import about


class About(unittest.TestCase):
    def test_version_matches_plugin(self):
        want = json.loads((KIT / ".claude-plugin" / "plugin.json").read_text())["version"]
        self.assertIn(f"Kit version: {want}\n", about.report())

    def test_no_home_path(self):
        self.assertNotIn(str(pathlib.Path.home()), about.report())


if __name__ == "__main__":
    unittest.main()
