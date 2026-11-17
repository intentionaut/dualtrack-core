"""docs/release-notes.md as a check: what it keeps out, and what it lets through."""
import pathlib
import sys
import unittest

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
import loop_lib

GOOD = """## 1.2.0 - 2026-11-03

Changed:
- Add `decide.py`, which records the owner's call from the morning brief.
- Stop list reads an item's title and Done when lines only.

Breaking:
- none

Upgrade:
- Copy `scripts/` again: `cp -R ../dualtrack/scripts .`

Check:
- `python3 -m unittest discover -s tests` passes.
"""


class Notes(unittest.TestCase):
    def test_a_good_note_passes(self):
        self.assertEqual(loop_lib.notes(GOOD), [])

    def test_keeps_out_what_must_never_ship(self):
        for bad, why in (("- Set token: ghp_abcdefghijklmnopqrstuvwx1234", "a secret"),
                         ("- Thanks to jo@example.com for the report.", "an email address"),
                         ("- Fixed a path in /home/jo/projects/kit.", "a home path"),
                         ("- Let me explain what changed here.", "a chat log"),
                         ("User: can you fix this?", "a chat log"),
                         ("- Built on team/2026-11-03-101010.", "a team branch")):
            self.assertIn(why, loop_lib.notes(GOOD + bad + "\n"), bad)

    def test_needs_the_agent_shape(self):
        self.assertTrue(any("Check:" in p for p in loop_lib.notes(GOOD.replace("Check:", "Notes:"))))
        self.assertTrue(any("heading" in p for p in loop_lib.notes(GOOD.replace("1.2.0 - 2026-11-03", "Big release!"))))
        self.assertIn("a release section", loop_lib.notes("We shipped lots of things."))

    def test_long_lines_and_lists_are_refused(self):
        long = GOOD.replace("- Stop list", "- " + "word " * 30 + "Stop list")
        self.assertTrue(any("25 words" in p for p in loop_lib.notes(long)))
        many = GOOD.replace("Changed:\n", "Changed:\n" + "- Add a thing.\n" * 10)
        self.assertTrue(any("ten Changed" in p for p in loop_lib.notes(many)))

    def test_plain_words_like_token_count_pass(self):
        self.assertEqual(loop_lib.notes(GOOD.replace("Stop list reads", "Token counts and the stop list read")), [])

    def test_a_products_own_changelog_is_judged_for_privacy_only(self):
        own = "## 0.3.3 (2026-11-05)\n\n### Changed\n- Keywords for DESIGN.md searches\n"
        self.assertEqual(loop_lib.notes(own, house=False), [])
        self.assertIn("a team branch", loop_lib.notes(own + "- built on team/2026-11-05-1200\n", house=False))
        self.assertTrue(loop_lib.notes(own))
