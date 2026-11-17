"""Every scripts/*.py parses on the oldest Python the README promises (3.9).

CI runs 3.12, which accepts syntax that 3.9 to 3.11 reject (a backslash inside
an f-string expression crashed setup on a stock Mac). This compiles each script
with an older interpreter when one is installed, and says so when none is.
"""
import pathlib
import shutil
import subprocess
import sys
import unittest

KIT = pathlib.Path(__file__).resolve().parent.parent
CHECK = "import sys; [compile(open(f, encoding='utf-8').read(), f, 'exec') for f in sys.argv[1:]]"


def old_python():
    """An interpreter older than 3.12, or None."""
    for exe in ("python3.9", "python3.10", "python3.11", "/usr/bin/python3"):
        path = shutil.which(exe)
        if not path:
            continue
        v = subprocess.run([path, "-c", "import sys; print(sys.version_info[:2] < (3, 12))"],
                           capture_output=True, text=True)
        if v.stdout.strip() == "True":
            return path
    return None


class OldPythonSyntax(unittest.TestCase):
    def test_every_script_compiles_on_old_python(self):
        exe = old_python()
        if not exe:
            self.skipTest("no Python older than 3.12 installed; CI checks 3.9 in its own step")
        files = sorted(str(p) for p in (KIT / "scripts").glob("*.py"))
        self.assertTrue(files)
        r = subprocess.run([exe, "-c", CHECK, *files], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, f"{exe} cannot compile a script:\n{r.stderr}")


if __name__ == "__main__":
    unittest.main()
