"""Agent and skill frontmatter parses as YAML: a bare ": " inside a plain value ends the mapping (directory review)."""
import pathlib
import re
import unittest

KIT = pathlib.Path(__file__).resolve().parent.parent


class Frontmatter(unittest.TestCase):
    def test_no_plain_value_holds_a_colon_and_space(self):
        bad = []
        for f in [*KIT.glob("agents/*.md"), *KIT.glob("skills/*/SKILL.md"), *KIT.glob("commands-adapted/*.md")]:
            m = re.match(r"---\n(.*?)\n---", f.read_text(), re.S)
            for line in (m.group(1).splitlines() if m else []):
                key, sep, value = line.partition(": ")
                value = value.strip()
                if sep and value and value[0] not in "\"'|>[{" and ": " in value:
                    bad.append(f"{f.relative_to(KIT)}: {key}")
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
