"""Every reader of the profile drops setup's notes and agrees on the value."""
import pathlib
import subprocess
import sys
import tempfile
import unittest

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
import profile_value  # noqa: E402

PROFILE = ("**Repo:** . (confirmed: run)\r\n**Mode:** acquisition (inferred: x), optimisation\n"
           "**Context path:** ./ctx (inferred: default)\n**Context store:** local (confirmed: owner)\n"
           "**Test commands:** make test (fast)\n**Required checks:** test, lint (confirmed: ci.yml)\n"
           "**Sources:** none (inferred: no counts)\n**New idea slots:** 1 (default)\n"
           "**Visitor paths:** ^src/pages/ (confirmed: owner)\n**Note:** churn (inferred: a (b) c)\n")


class ProfileValue(unittest.TestCase):
    def test_notes_drop_and_other_brackets_stay(self):
        f = lambda n: profile_value.field(PROFILE, n)
        self.assertEqual(f("Repo"), ".")
        self.assertEqual(f("Mode"), "acquisition, optimisation")
        self.assertEqual(f("Context path"), "./ctx")
        self.assertEqual(f("Test commands"), "make test (fast)")
        self.assertEqual(f("Required checks"), "test, lint")
        self.assertEqual(f("New idea slots"), "1")
        self.assertEqual(f("Note"), "churn")
        self.assertEqual(f("Missing"), "")

    def test_the_shell_readers_agree(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "profile.md"
            p.write_text(PROFILE)
            for script, var in (("run.sh", "PROFILE"), ("daily_loop.sh", "RUN")):
                line = next(l for l in (KIT / "scripts" / script).read_text().splitlines() if l.startswith("field()"))
                path = str(p) if var == "PROFILE" else d
                for name in ("Repo", "Mode", "Context path", "Test commands", "Required checks", "Note"):
                    out = subprocess.run(["bash", "-c", f'KIT="{KIT}"; {var}="{path}"; {line}; field "{name}"'],
                                         capture_output=True, text=True).stdout.strip()
                    self.assertEqual(out, profile_value.field(PROFILE, name), f"{script} {name}")

    def test_the_hunters_cases(self):
        # Each case broke a real reader on 2026-11-12, found by a sweep with annotated profiles.
        import loop_lib, merge_gate, file_setup, setup_apply, sources
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d) / "p.md"
            p.write_text("**Sources:** none (inferred: no counts)\n")
            self.assertEqual(sources.names(str(p)), [])
        self.assertEqual(merge_gate.field("**Required checks:** test, lint (confirmed: ci.yml)\n", "Required checks"), "test, lint")
        self.assertEqual(loop_lib.lane("**Visitor paths:** ^src/pages/ (confirmed: owner)\n", "M\tsrc/pages/index.html"),
                         "src/pages/index.html")
        self.assertIsNone(loop_lib.protected("**Protected text:** LICENSE :: MIT License (confirmed: owner)\n",
                                             ["x"], lambda _: "MIT License"))
        self.assertIn("optimisation", file_setup.fill("# P\n\n**Mode:** optimisation (inferred: churn < 5%)\n"))
        self.assertIn(r"pytest -k 'a\d'", setup_apply.set_line("**Test commands:** x\n", "Test commands", r"pytest -k 'a\d'"))

    def test_no_script_reads_a_profile_line_with_its_own_regex(self):
        own = [f.name for f in (KIT / "scripts").glob("*.py") if f.name not in ("profile_value.py", "file_setup.py")
               and ':\\*\\* *(.*)$"' in f.read_text()]
        self.assertEqual(own, [])


if __name__ == "__main__":
    unittest.main()
