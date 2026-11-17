"""A repo with tests/ and no __init__.py is not told its tests fail: setup picks a unittest command that can import them."""
import importlib.util
import os
import pathlib
import subprocess
import sys
import unittest
from unittest import mock

try:
    import scratch
except ImportError:
    from tests import scratch

KIT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("setup_check", KIT / "scripts/setup_check.py")
setup_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup_check)

TEST = "import unittest\nfrom pkg import f\n\nclass T(unittest.TestCase):\n    def test_a(self):\n        self.assertEqual(f(), 1)\n"


class Discovery(unittest.TestCase):
    def repo(self, init):
        d = pathlib.Path(scratch.mkdtemp())
        (d / "pkg").mkdir(); (d / "pkg/__init__.py").write_text("def f():\n    return 1\n")
        (d / "tests").mkdir(); (d / "tests/test_a.py").write_text(TEST)
        if init:
            (d / "tests/__init__.py").write_text("")
        return d

    def command_in(self, d):
        old = os.getcwd()
        os.chdir(d)
        try:  # pytest hidden, so the unittest branch is the one under test
            with mock.patch.object(setup_check.shutil, "which", return_value=None), \
                 mock.patch.object(setup_check, "sh", return_value=(1, "")):
                return setup_check.test_command()
        finally:
            os.chdir(old)

    def run_it(self, d, command):
        return subprocess.run(command.replace("python3", sys.executable, 1), shell=True, cwd=d, capture_output=True, text=True)

    def test_tests_folder_without_init_runs_green(self):
        d = self.repo(init=False)
        cmd = self.command_in(d)
        r = self.run_it(d, cmd)
        self.assertEqual(r.returncode, 0, f"{cmd}\n{r.stderr}")
        self.assertEqual(setup_check.tests_ran(r.stderr + r.stdout), 1)

    def test_tests_folder_with_init_keeps_the_top_level_flag(self):
        d = self.repo(init=True)
        cmd = self.command_in(d)
        self.assertIn("-t .", cmd)
        self.assertEqual(self.run_it(d, cmd).returncode, 0)


if __name__ == "__main__":
    unittest.main()
