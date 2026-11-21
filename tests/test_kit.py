"""Run: python3 tests/test_kit.py. Fails on personal detail or a missing mode."""
import json
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
BANNED = re.compile(r"/Users/(?![<|])|~/Documents|~/Projects|\b\d{9}\b", re.I)
# Personal and private-project terms live in a gitignored file, one regex per line, so the public repo never names them.
PRIVATE = ROOT / ".private-names"
PRIVATE_NAMES = [l.strip() for l in PRIVATE.read_text().splitlines() if l.strip() and not l.startswith("#")] if PRIVATE.exists() else []
PRIVATE_BANNED = re.compile("|".join(PRIVATE_NAMES), re.I) if PRIVATE_NAMES else None
if PRIVATE_BANNED is None:
    print("test_kit: .private-names not found, skipping the private-name check", file=sys.stderr)
MODES = ("acquisition", "activation", "optimisation")
MOVES = ("Fix", "Reach", "Capture", "Offer", "Distribute", "Compound", "Prove", "Learn")
MOVE_FIELDS = ("Question", "Fits when", "Evidence", "Output", "Not when")
PROFILE_FIELDS = ("Repo", "Audience", "Goal", "Channels", "Moves off", "Constraints")
CONTRACT = (
    "Product manager brief, <YYYY-MM-DD>: ok | gaps | unknown",
    "Runners-up:",
    "Learn cannot win two runs in a row",
    "Product manager memo, <YYYY-MM-DD>: ok | gaps | unknown",
    "Product manager daily, <YYYY-MM-DD>: quiet | changed | unknown",
    "Cadence: weekly",
    "Cadence: daily",
    "Record:",
)
SKIP = {"test_kit.py", ".private-names", "CLAUDE.md", "LICENSE", "NOTICE", "TRADEMARKS.md", "SECURITY.md", "CODE_OF_CONDUCT.md", "config.yml", "CITATION.cff", "feedback.json", "plugin.json", "marketplace.json"}  # CLAUDE.md is the maintainer's build-log note; the rest are credit and contact metadata


def files():
    for p in ROOT.rglob("*"):
        if p.is_file() and ".git" not in p.parts and ".claude" not in p.parts and "__pycache__" not in p.parts and p.name not in SKIP and not p.name.endswith("-LOG.md"):
            yield p


def main():
    errors = []
    for p in files():
        try:
            text = p.read_text()
        except UnicodeDecodeError:
            continue  # binary files (the plugin icon) carry no words to check
        for n, line in enumerate(text.splitlines(), 1):
            if p.name == "README.md" and line.endswith("<!-- credit -->"):
                continue  # the two credit lines are the only place the author's name belongs
            hit = BANNED.search(line) or (PRIVATE_BANNED and PRIVATE_BANNED.search(line))
            if hit:
                errors.append(f"{p.relative_to(ROOT)}:{n}: {hit.group()}")
    pm = (ROOT / "agents/product-manager.md").read_text()
    readme = (ROOT / "README.md").read_text()
    for m in MODES:
        if f"**{m}**" not in pm:
            errors.append(f"product-manager.md: no {m} mode")
        if not (ROOT / f"example/memos/{m}.md").exists():
            errors.append(f"example/memos/{m}.md missing")
    for line in CONTRACT:
        if line not in pm:
            errors.append(f"product-manager.md: no contract line: {line}")
    for m in MOVES:
        if f"- **{m}**" not in pm:
            errors.append(f"product-manager.md: no {m} move")
    moves = (ROOT / "moves.md").read_text()
    for m in MOVES:
        part = re.search(rf"^## {m}\n(.*?)(?=^## |\Z)", moves, re.M | re.S)
        for field in MOVE_FIELDS:
            if not part or not re.search(rf"^{field}: \S", part.group(1), re.M):
                errors.append(f"moves.md: {m} has no {field}")
    template = (ROOT / "profile.template.md").read_text()
    for field in PROFILE_FIELDS:
        if f"**{field}:**" not in template:
            errors.append(f"profile.template.md: no {field}")
    if not (ROOT / "agents/setup.md").exists():
        errors.append("agents/setup.md missing")
    # The plugin: agents load from the default agents/ scan only, so the manifest must not list them.
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
    if plugin.get("name") != "dualtrack" or "agents" in plugin:
        errors.append("plugin.json: name must be dualtrack, with no agents key")
    if sorted(p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md")) != ["ask-dualtrack", "dualtrack", "dualtrack-connect", "dualtrack-request", "dualtrack-setup", "dualtrack-team"]:
        errors.append("skills/: only ask-dualtrack, dualtrack, dualtrack-connect, dualtrack-request, dualtrack-setup and dualtrack-team ship to users")
    setup = (ROOT / "skills/dualtrack-setup/SKILL.md").read_text()
    for line in ("A private record repo (Recommended)", "If it is PUBLIC", "setup_check.py", "setup_apply.py", "AskUserQuestion",
                 "docs/schedule.md", "You cannot set up the schedule yourself"):
        if line not in setup:
            errors.append(f"skills/dualtrack-setup/SKILL.md: no {line}")
    for path in [p.rstrip(".") for p in re.findall(r"<kit>/([\w./-]+)", setup)]:
        if not (ROOT / path).exists():
            errors.append(f"skills/dualtrack-setup/SKILL.md names a missing file: {path}")
    for f in ("core", "cli", "web", "docs", "checklists", "writing"):
        if not (ROOT / f"standards/{f}.md").exists():
            errors.append(f"standards/{f}.md missing")
    design = (ROOT / "agents/product-design.md").read_text()
    if "First line exactly `DESIGN` or `BLOCKED: <reason>`" not in design:
        errors.append("product-design.md: no contract line")
    ux = (ROOT / "agents/ux-review.md").read_text()
    for line in ("UX audit, <YYYY-MM-DD>: ok | gaps", "first line exactly `APPROVE` or `CHANGES`", "Rate severity on the core scale"):
        if line not in ux:
            errors.append(f"ux-review.md: no contract line: {line}")
    for step in ("watch", "research", "decide"):
        if f"**{step}**" not in pm:
            errors.append(f"product-manager.md: no {step} step")
    if "**Routing:**" not in (ROOT / "profile.template.md").read_text():
        errors.append("profile.template.md: no Routing line")
    if "—" in readme:
        errors.append("README.md: em dash")
    for e in errors:
        print(e)
    if errors:
        return 1
    print(f"ok: {len(MODES)} modes")
    return 0


class Kit(unittest.TestCase):
    def test_no_personal_detail_and_every_mode(self):
        self.assertEqual(main(), 0)

    def test_privacy_copy_never_claims_nothing_leaves_the_machine(self):
        # Claude reads what each step needs through the owner's plan, so the claim is false.
        for p in [*ROOT.glob("skills/*/SKILL.md"), *ROOT.glob("docs/*.md"), ROOT / "README.md", *ROOT.glob("scripts/*.py")]:
            self.assertNotRegex(p.read_text().lower(), r"nothing (ever )?leaves", p.name)

    def test_setup_shows_skill_cards_with_a_consequence_note(self):
        setup = (ROOT / "skills/dualtrack-setup/SKILL.md").read_text()
        for card in ("⚙ Setup", "◆ Planning", "⛨ Safety check", "↳"):
            self.assertIn(card, setup)
        self.assertIn("numbers.md", setup)  # the numbers step offers the paste option
        self.assertIn("No Dualtrack server", setup)  # the privacy card
        writing = (ROOT / "standards/writing.md").read_text()
        for rule in ("**The product speaks**", "**Action, then consequence**", "**Privacy, exactly**"):
            self.assertIn(rule, writing)

    def test_the_kit_reports_one_version_everywhere(self):
        version = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())["version"]
        self.assertIn(f'"name": "dualtrack", "version": "{version}"', (ROOT / "scripts/mcp_server.py").read_text())

    def test_the_name_policy_is_on_main_and_linked_from_readme_and_notice(self):
        policy = (ROOT / "TRADEMARKS.md").read_text()
        for want in ("Trademark clause", "based on Dualtrack", "Call a changed copy Dualtrack"):
            self.assertIn(want.lower(), policy.lower(), want)
        for name in ("README.md", "NOTICE"):
            self.assertIn("TRADEMARKS.md", (ROOT / name).read_text(), name)

    def test_the_daily_workflow_leaves_no_token_in_the_checkout(self):
        wf = (ROOT / ".github/workflows/daily.yml").read_text()
        self.assertRegex(wf, r"persist-credentials:\s*false")
        self.assertIn("gh auth setup-git", wf)

    def test_the_daily_workflow_can_start_the_linux_sandbox(self):
        # Company mode stops on Linux without it, so every cloud run would stop before any work
        wf = (ROOT / ".github/workflows/daily.yml").read_text()
        self.assertIn("apt-get install -y -q bubblewrap", wf)
        self.assertIn("kernel.apparmor_restrict_unprivileged_userns=0", wf)

    def test_no_workflow_checkout_leaves_the_token_in_git_settings(self):
        # Branch code runs in these jobs; a persisted token in .git/config is one read away.
        for wf in sorted((ROOT / ".github/workflows").glob("*.yml")):
            steps = wf.read_text().split("- uses: ")[1:]
            for step in (s for s in steps if s.startswith("actions/checkout@")):
                self.assertIn("persist-credentials: false", step.split("\n      - ")[0], wf.name)

    def test_the_daily_workflow_restores_one_exact_cache_key(self):
        # a prefix match would pick up whichever earlier run saved last, a poisoned one included
        self.assertNotIn("restore-keys", (ROOT / ".github/workflows/daily.yml").read_text())

    def test_every_workflow_pins_what_it_runs(self):
        # a tag or an unversioned install can be moved under us; the daily workflow holds a token
        for wf in (ROOT / ".github/workflows").glob("*.yml"):
            for line in wf.read_text().splitlines():
                uses = re.search(r"uses:\s*(\S+)", line)
                if uses:
                    self.assertRegex(uses.group(1), r"@[0-9a-f]{40}$", f"{wf.name}: {line.strip()}")
                if "npm install" in line or "pip install" in line:
                    self.assertRegex(line, r"(@|==)\d", f"{wf.name}: {line.strip()}")

    def test_the_automatic_track_is_bounded_by_risk_not_size(self):
        # the owner's rule: any size if no person sees it and the stop list is untouched; size only gates the plan
        for rel in ("README.md", ".claude-plugin/plugin.json", "scripts/daily_loop.sh", "skills/dualtrack-setup/SKILL.md"):
            self.assertNotIn("low-level", (ROOT / rel).read_text(), rel)
        pm = " ".join((ROOT / "agents/product-manager.md").read_text().split())
        self.assertNotIn("Choose something small", pm)
        self.assertIn("any size", " ".join((ROOT / "README.md").read_text().split()))
        self.assertIn("any size", pm)


if __name__ == "__main__":
    sys.exit(main())
