"""The router names only commands and skills that exist, and only decide commands decide.py takes."""
import pathlib
import re
import sys
import unittest

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
import decide

ROUTER = (KIT / "skills/ask-dualtrack/SKILL.md").read_text()


class Router(unittest.TestCase):
    def test_every_script_and_doc_it_names_exists(self):
        named = set(re.findall(r"\b((?:scripts|docs)/[\w.-]+\.(?:py|sh|md))", ROUTER))
        self.assertTrue(named)
        self.assertEqual([p for p in sorted(named) if not (KIT / p).exists()], [])

    def test_every_skill_it_names_exists(self):
        skills = {m for m in re.findall(r"`/([\w-]+)`", ROUTER)}
        self.assertEqual(sorted(s for s in skills if not (KIT / "skills" / s / "SKILL.md").exists()), [])

    def test_every_decide_command_it_names_is_real(self):
        used = set(re.findall(r"decide\.py (\w+)", ROUTER))
        known = set(re.findall(r"^\s*decide\.py (\w+)", decide.__doc__, re.M)) | {"1"}
        self.assertEqual(sorted(used - known), [])


if __name__ == "__main__":
    unittest.main()
