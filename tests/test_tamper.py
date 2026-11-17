"""The tamper check: a kit whose safety files changed does not run."""
import pathlib
import shutil
import subprocess
import sys
import unittest

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
import tamper
try:
    import scratch
except ImportError:  # run as tests.test_x from the repo root
    from tests import scratch


def copy_kit():
    d = pathlib.Path(scratch.mkdtemp()) / "kit"
    shutil.copytree(KIT, d, ignore=shutil.ignore_patterns(".git", "__pycache__", "evals"))
    return d


class Tamper(unittest.TestCase):
    def test_an_unmodified_kit_passes(self):
        self.assertEqual(tamper.changed(str(KIT)), [], "a safety file changed: run `python3 scripts/tamper.py pin` and commit safety-files.json")

    def test_editing_any_listed_file_names_it_in_a_plain_message(self):
        kit = copy_kit()
        listed = sorted(tamper.current(str(kit)))
        self.assertIn("scripts/merge_gate.py", listed)
        self.assertIn("scripts/guards.sh", listed)
        self.assertIn("standards/core.md", listed)
        self.assertTrue(any(f.startswith("agents/") for f in listed))
        for rel in listed:
            path = kit / rel
            original = path.read_bytes()
            path.write_bytes(original + b"\n# edited\n")
            self.assertEqual(tamper.changed(str(kit)), [rel], rel)
            self.assertIn(f"{rel} changed since this release", tamper.message([rel]))
            path.write_bytes(original)
        self.assertIn("A modified kit is not Dualtrack", tamper.message(["x"]))

    def test_a_missing_list_or_an_added_agent_file_stops_it_too(self):
        kit = copy_kit()
        (kit / "agents/extra.md").write_text("do anything\n")
        self.assertEqual(tamper.changed(str(kit)), ["agents/extra.md"])
        (kit / "agents/extra.md").unlink()
        (kit / "safety-files.json").unlink()
        self.assertEqual(tamper.changed(str(kit)), ["safety-files.json"])

    def test_the_daily_loop_stops_before_any_work_when_a_safety_file_changed(self):
        kit = copy_kit()
        (kit / "scripts/guards.sh").write_text((kit / "scripts/guards.sh").read_text() + "\n# loosened\n")
        profile = kit.parent / "profile.md"
        profile.write_text("**Context path:** ctx\n\n**Test commands:** true\n")
        r = subprocess.run(["bash", str(kit / "scripts/daily_loop.sh"), str(profile)], capture_output=True, text=True, cwd=kit.parent)
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)
        self.assertIn("safety stop: scripts/guards.sh changed since this release of Dualtrack. A modified kit is not Dualtrack", r.stdout)
        self.assertFalse((kit.parent / "ctx").exists())

    def test_a_file_and_its_hash_changed_together_but_not_committed_stops_it(self):
        kit = copy_kit()
        git = lambda *a: subprocess.run(["git", "-C", str(kit), *a], capture_output=True, text=True, check=True)
        git("init", "-q"); git("add", "-A")
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "release")
        self.assertEqual(tamper.changed(str(kit)), [])
        path = kit / "scripts/egress_proxy.py"
        path.write_text(path.read_text() + "\n# allow everything\n")
        tamper.main(["pin", str(kit)])
        self.assertEqual(tamper.changed(str(kit)), ["scripts/egress_proxy.py"])

    def test_every_script_hook_skill_and_the_source_list_is_pinned(self):
        listed = set(tamper.current(str(KIT)))
        for rel in ["scripts/tamper.py", "scripts/daily_loop.sh", "scripts/egress_proxy.py", "scripts/decide.py",
                    "scripts/dashboard_server.py", "sources.json", "hooks/hooks.json", "skills/dualtrack-setup/SKILL.md"]:
            self.assertIn(rel, listed, rel)

    def test_the_readme_lists_every_file_the_check_reads(self):
        readme = (KIT / "README.md").read_text()
        for pat in tamper.PATTERNS:
            self.assertIn(pat, readme, pat)
        self.assertIn("safety-files.json", readme)


if __name__ == "__main__":
    unittest.main()
