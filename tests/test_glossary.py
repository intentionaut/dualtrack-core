"""The glossary in code: an agent is never "PM", so a reader can tell it from a human product manager."""
import pathlib
import re
import sys
import unittest

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
import loop_lib  # noqa: E402
PM = re.compile(r"\bPM:")
# "The team" is people and agents. These say only an agent acted, so they must name Dualtrack agents or a role.
AGENT_ONLY = re.compile(r"\bthe team(?:'s (?:pull request|worktree|record|state|memo|branch)"
                        r"| (?:builds|built|opens|opened|merges|merged|runs|ran|stopped|stops|held|reads|pushes|pushed)\b)", re.I)
SCAN = ("README.md", "agents", "prompts", "scripts", "skills", "commands-adapted", ".github", "docs")


def offenders(root, pattern=PM):
    hits = []
    for top in SCAN:
        base = root / top
        for f in [base] if base.is_file() else sorted(base.rglob("*")) if base.exists() else []:
            if f.is_file() and f.suffix in {".md", ".py", ".sh", ".yml", ".json"}:
                for n, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
                    if pattern.search(line):
                        hits.append(f"{f.relative_to(root)}:{n}")
    return hits


class Glossary(unittest.TestCase):
    def test_no_agent_is_called_pm(self):
        self.assertEqual(offenders(KIT), [])

    def test_the_check_catches_pm(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            (pathlib.Path(d) / "scripts").mkdir()
            (pathlib.Path(d) / "scripts/x.py").write_text('made = [f"PM: {why}"]\n')
            self.assertEqual(offenders(pathlib.Path(d)), ["scripts/x.py:1"])

    def test_agent_only_work_never_says_the_team(self):
        self.assertEqual(offenders(KIT, AGENT_ONLY), [])

    def test_the_team_check_keeps_shared_work_and_catches_agent_work(self):
        for keep in ("The team weighs in on the backlog.", "the team's view", "the team decides", "Dualtrack agents build it."):
            self.assertIsNone(AGENT_ONLY.search(keep), keep)
        for catch in ("The team builds your pick.", "the team's pull request", "the team merged it", "The team opens a PR"):
            self.assertIsNotNone(AGENT_ONLY.search(catch), catch)

    def test_readme_points_to_the_glossary(self):
        self.assertIn("docs/glossary.md", (KIT / "README.md").read_text())
        self.assertTrue((KIT / "docs/glossary.md").exists())

    def test_every_agent_has_a_glossary_name_and_no_name_is_stale(self):
        self.assertEqual(set(loop_lib.ROLES), {f.stem for f in (KIT / "agents").glob("*.md")})
        glossary = (KIT / "docs/glossary.md").read_text()
        for file, name in loop_lib.ROLES.items():
            self.assertRegex(glossary, rf"\| `{re.escape(file)}` \| {re.escape(name)} \|")

    def test_every_trail_line_names_who_did_it(self):
        facts = {"item": {k: k for k in ("why", "what", "how_to_check", "decision", "watching")}, "repo_url": "https://x/o/r",
                 "commits": [{"sha": "a" * 40, "subject": "s"}], "failed_first": "failed", "tests": "passed",
                 "verdicts": ["CHANGES", "APPROVE"], "ux_verdicts": ["APPROVE"]}
        body = loop_lib.trail(facts, (KIT / ".github/pull_request_template.md").read_text())
        self.assertEqual(loop_lib.unattributed(body), [])
        self.assertTrue(body.startswith("Decided by: Dualtrack agents. Proposed by the Dualtrack product manager"))
        signed = loop_lib.trail(dict(facts, decided_by="Ada"), (KIT / ".github/pull_request_template.md").read_text())
        self.assertTrue(signed.startswith("Decided by: Ada. "))

    def test_decided_by_shows_a_name_only_when_the_profile_says_so(self):
        bets = "- 2026-11-01 | Fix it | confirmed | by: Ada\n- 2026-11-01 | Other | proposed | [[memos/m]]\n"
        self.assertEqual(loop_lib.decided_by(bets, "Fix it", False), "the owner")
        self.assertEqual(loop_lib.decided_by(bets, "Fix it", True), "Ada")
        self.assertEqual(loop_lib.decided_by(bets, "Unknown", False), "")

    def test_the_run_check_refuses_a_line_with_no_author(self):
        body = "## How this was made\n- Dualtrack navigator, round 1: APPROVE\n- Navigator, round 2: APPROVE\n- PM: why\n"
        self.assertEqual(loop_lib.unattributed(body), ["- Navigator, round 2: APPROVE", "- PM: why"])
        self.assertIn("a named author for: PM: why", loop_lib.check(body, str(KIT)))


if __name__ == "__main__":
    unittest.main()
