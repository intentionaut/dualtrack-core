import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

TESTS = pathlib.Path(__file__).resolve().parent


class Scratch(unittest.TestCase):
    def made_by(self, code):
        home = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, home, True)
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=dict(os.environ, TMPDIR=home, PYTHONPATH=str(TESTS)))
        self.assertEqual(r.returncode, 0, r.stderr)
        return os.listdir(home)

    def test_a_folder_made_through_scratch_is_gone_when_the_process_ends(self):
        self.assertEqual(self.made_by("import scratch; scratch.mkdtemp()"), [])

    def test_a_plain_mkdtemp_stays_which_is_why_the_tests_use_scratch(self):
        self.assertEqual(len(self.made_by("import tempfile; tempfile.mkdtemp()")), 1)

    def test_the_tests_make_their_folders_through_scratch(self):
        users = [p.name for p in TESTS.glob("test_*.py") if "tempfile.mkdtemp(" in p.read_text() and p.name != "test_scratch.py"]
        self.assertEqual(users, [])


if __name__ == "__main__":
    unittest.main()
