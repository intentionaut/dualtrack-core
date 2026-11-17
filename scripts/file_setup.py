#!/usr/bin/env python3
"""Turn the setup agent's message into profile.md and setup-notes.md, ready to run.

Usage: python3 scripts/file_setup.py <message.md> [--state <state repo>]   from the root of your repo
With --state, everything goes in <state repo>/<this repo's folder name>/, so one private repo holds the
record for every product and the product repo gets only code. Never overwrites an existing profile.md.
"""
import pathlib
import re
import profile_value  # noqa: E402
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import decide  # noqa: E402

KIT = pathlib.Path(__file__).resolve().parent.parent
DEFAULTS = {"Mode": "acquisition", "Context store": "local", "Context path": "./product-context",
            "Numbers file": "./numbers.md"}


def split(text):
    head, sep, notes = text.partition("Starting options:")
    return head.strip() + "\n", (sep + notes).strip() + "\n" if sep else ""


def fill(profile):
    for name, value in DEFAULTS.items():
        line = re.search(rf"^\*\*{name}:\*\* *(.*)$", profile, re.M)
        if not line:
            profile = profile.rstrip() + f"\n\n**{name}:** {value}\n"
        elif not (v := profile_value.clean(line[1])) or v.lower().startswith("unknown") or "|" in v or "<" in v:
            profile = profile.replace(line[0], f"**{name}:** {value}")
    # An optional line with no value must not read as one: "Copy source: unknown" would gate the engineer.
    profile = re.sub(r"^\*\*(?:Copy source|Notion page):\*\* *(?:unknown\b.*)?\n\n?", "", profile, flags=re.M | re.I)
    return runnable_tests(profile)


def runnable_tests(profile):
    """The loop runs Test commands as a shell line, so keep only the commands the agent quoted."""
    line = re.search(r"^\*\*Test commands:\*\* *(.*)$", profile, re.M)
    commands = re.findall(r"`([^`]+)`", profile_value.clean(line[1])) if line else []
    return profile.replace(line[0], "**Test commands:** " + " && ".join(commands)) if commands else profile


def main(argv):
    text = pathlib.Path(argv[0]).read_text()
    state = argv[argv.index("--state") + 1] if "--state" in argv else None
    home = pathlib.Path(state) / decide.repo_name() if state else pathlib.Path(".")
    profile_path = home / "profile.md"
    if not text.startswith("# Product profile") or profile_path.exists():
        print(f"unknown: not filed: the message is not a profile, or {profile_path} exists")
        return 2
    profile, notes = split(text)
    if state:
        # Paths stay relative to the product repo, so the same profile works locally and in a cloud routine.
        for name in ("Context path", "Numbers file"):
            DEFAULTS[name] = str(home / pathlib.Path(DEFAULTS[name]).name)
            profile = re.sub(rf"^\*\*{name}:\*\*.*\n?", "", profile, flags=re.M)
        profile = profile.rstrip() + f"\n\n**State repo:** {state}\n"
    home.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(fill(profile))
    (home / "setup-notes.md").write_text(notes)
    if not (home / "product-context").exists():
        shutil.copytree(KIT / "product-context", home / "product-context")
    if not (home / "numbers.md").exists():
        (home / "numbers.md").write_text("# Numbers\nPaste counts here. Write unknown where you have none.\n")
    where = f"{home}/" if state else ""
    print(f"filed: {where}profile.md, {where}setup-notes.md, {where}product-context/, {where}numbers.md")
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
