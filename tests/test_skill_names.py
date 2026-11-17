import re
import unittest
from pathlib import Path

SKILLS = Path(__file__).resolve().parent.parent / "skills"


def frontmatter_name(path):
    m = re.search(r"^name:\s*(\S+)\s*$", path.read_text().split("---")[1], re.M)
    return m.group(1) if m else None


class SkillNames(unittest.TestCase):
    def test_every_skill_is_named_after_dualtrack(self):
        for md in sorted(SKILLS.glob("*/SKILL.md")):
            name = frontmatter_name(md)
            self.assertIsNotNone(name, f"{md}: no name in frontmatter")
            self.assertIn("dualtrack", name, f"{md}: skill name must contain 'dualtrack'")
            self.assertEqual(md.parent.name, name, f"{md}: folder and frontmatter name differ")

    def test_front_door_exists(self):
        self.assertTrue((SKILLS / "dualtrack" / "SKILL.md").is_file(), "skills/dualtrack is missing")
        self.assertEqual(frontmatter_name(SKILLS / "dualtrack" / "SKILL.md"), "dualtrack")


if __name__ == "__main__":
    unittest.main()
