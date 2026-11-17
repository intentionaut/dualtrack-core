"""preview.py: the first brief before any setup question, labelled by code and written nowhere."""
import json
import os
import pathlib
import stat
import subprocess
import sys
import unittest
try:
    import scratch
except ImportError:  # run as tests.test_x from the repo root
    from tests import scratch

KIT = pathlib.Path(__file__).resolve().parent.parent
FAKE = '#!/usr/bin/env python3\nimport json, os, sys\njson.dump(sys.argv[1:], open(os.environ["FAKE_LOG"], "w"))\nprint(open(os.environ["FAKE_OUT"]).read())\n'
SAMPLE = [l[2:].strip() for l in (KIT / "example/sample-evidence.md").read_text().splitlines() if l.startswith("- ")]


class Preview(unittest.TestCase):
    def setUp(self):
        self.t = pathlib.Path(scratch.mkdtemp())
        self.claude = self.t / "claude"; self.claude.write_text(FAKE); self.claude.chmod(self.claude.stat().st_mode | stat.S_IEXEC)
        self.repo = self.t / "shop"; self.repo.mkdir()
        (self.repo / "README.md").write_text("# Shop\n\nShop lets small bakeries take orders online and see what sells each week.\n")
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=t", "-c", "user.email=t@t.invalid", "commit", "-qm", "init"], check=True)

    def preview(self, bets, **out):
        (self.t / "out.json").write_text(json.dumps(dict({"structured_output": {"bets": bets}, "total_cost_usd": 0.04}, **out)))
        r = subprocess.run([sys.executable, str(KIT / "scripts/preview.py")], cwd=self.repo, capture_output=True, text=True,
                           env=dict(os.environ, CLAUDE=str(self.claude), FAKE_OUT=str(self.t / "out.json"), FAKE_LOG=str(self.t / "args.json")))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout, json.loads(r.stdout.strip().splitlines()[-1])

    def test_at_most_three_bets_each_on_known_evidence_and_sample_labelled_by_code(self):
        out, facts = self.preview([
            {"title": "Weekly best-seller email", "why": "Bakers want to see what sells.", "evidence": ["R1"]},
            {"title": "Shorter sign-up", "why": "Most never finish.", "evidence": ["S1"]},
            {"title": "Made up", "why": "No evidence.", "evidence": ["X9"]},
            {"title": "Fourth\nline", "why": "x", "evidence": ["R1"]}])
        self.assertEqual(facts["bets"], ["Weekly best-seller email", "Shorter sign-up"])
        self.assertIn("2. Shorter sign-up (Sample)", out); self.assertIn("Sample: " + SAMPLE[0], out)
        self.assertIn("1. Weekly best-seller email\n", out); self.assertIn("From your repo: Shop lets small bakeries", out)
        self.assertNotIn("Made up", out); self.assertNotIn("Fourth", out)
        self.assertIn("A bet is one change the team expects to move a number you care about", out)

    def test_long_fields_are_cut_at_a_word_and_evidence_at_two_lines(self):
        out, facts = self.preview([{"title": "one two three four five six seven eight nine ten", "why": " ".join(["word"] * 40),
                                    "evidence": ["R1", "S1", "S2"]}])
        self.assertEqual(facts["bets"], ["one two three four five six seven eight…"])
        self.assertIn("Why: " + " ".join(["word"] * 25) + "…\n", out)
        self.assertIn("Sample: " + SAMPLE[0], out); self.assertNotIn(SAMPLE[1], out)

    def test_a_title_cannot_forge_another_line(self):
        out, facts = self.preview([{"title": "A\n2. Fake bet", "why": "y", "evidence": ["R1"]}])
        self.assertNotIn("\n2. Fake bet", out); self.assertEqual(len(facts["bets"]), 1)

    def test_a_title_is_safe_inside_the_focus_command(self):
        planted = self.t / "PLANTED"
        out, facts = self.preview([{"title": f'Faster sign-up $(touch {planted}) `id` "x" \\', "why": "y", "evidence": ["R1"]}])
        title = facts["bets"][0]
        self.assertFalse(set(title) & set('$`"\\'), title)
        subprocess.run(["bash", "-c", f'echo --focus "{title}"'], capture_output=True)
        self.assertFalse(planted.exists())

    def test_links_secrets_and_odd_model_output_never_reach_the_prompt_or_crash(self):
        docs = self.repo / "docs"; docs.mkdir()
        key = self.t / "key.txt"; key.write_text("Our deploy notes for the shop team: token ghp_" + "a1B2c3D4" * 5 + "\n")
        (docs / "linked.md").symlink_to(key); (docs / "gone.md").symlink_to(self.t / "missing.md")
        (docs / "notes.md").write_text("Ops notes for the shop team, kept in the repo: ghp_" + "Z9y8X7w6" * 5 + "\n")
        out, facts = self.preview([{"title": "T", "why": "y", "evidence": ["R1"]}])
        sent = (self.t / "args.json").read_text()
        self.assertNotIn("ghp_", sent); self.assertIn("bakeries", sent)
        for odd in ([], "text", {"structured_output": []}):
            (self.t / "out.json").write_text(json.dumps(odd))
            r = subprocess.run([sys.executable, str(KIT / "scripts/preview.py")], cwd=self.repo, capture_output=True, text=True,
                               env=dict(os.environ, CLAUDE=str(self.claude), FAKE_OUT=str(self.t / "out.json"), FAKE_LOG=str(self.t / "args.json")))
            self.assertEqual(r.returncode, 0, r.stderr); self.assertIn("No preview this time", r.stdout)

    def test_the_call_has_no_tools_a_cap_and_the_repo_as_untrusted_data(self):
        self.preview([])
        args = json.loads((self.t / "args.json").read_text())
        self.assertEqual(args[args.index("--tools") + 1], "")
        self.assertEqual(args[args.index("--max-budget-usd") + 1], "0.20")
        self.assertIn("--setting-sources=", args); self.assertIn("--disable-slash-commands", args)
        prompt = args[args.index("-p") + 1]
        self.assertIn("<untrusted>", prompt); self.assertIn("R1: Shop lets small bakeries", prompt); self.assertIn("S1: " + SAMPLE[0], prompt)

    def test_it_writes_nothing_and_says_so_when_there_is_nothing_to_show(self):
        out, facts = self.preview([])
        self.assertIn("No preview this time", out); self.assertEqual(facts["bets"], [])
        self.assertEqual(sorted(p.name for p in self.repo.iterdir()), [".git", "README.md"])
        self.assertEqual(subprocess.run(["git", "-C", str(self.repo), "status", "--porcelain"], capture_output=True, text=True).stdout, "")

    def test_a_picked_bet_goes_to_setup_as_the_focus_and_no_sample_line_reaches_the_record(self):
        self.preview([{"title": "Shorter sign-up", "why": "Most never finish.", "evidence": ["S1"]}])
        (self.repo / "setup.md").write_text("# Product profile\n\n**Mode:** acquisition\n\nStarting options:\n- x\n")
        r = subprocess.run([sys.executable, str(KIT / "scripts/setup_apply.py"), "--record", "state", "--runs", "local", "--ponytail", "no",
                            "--code-review", "no", "--auto-merge", "no", "--design", "no", "--focus", "Shorter sign-up"],
                           cwd=self.repo, capture_output=True, text=True,
                           env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t.invalid", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t.invalid"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        state = self.t / "dualtrack-state"
        self.assertIn("**Focus:** Shorter sign-up", (state / "shop/profile.md").read_text())
        record = "".join(p.read_text(errors="replace") for p in state.rglob("*") if p.is_file() and ".git" not in p.parts)
        for line in SAMPLE:
            self.assertNotIn(line, record)


if __name__ == "__main__":
    unittest.main()
