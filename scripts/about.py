"""Print the kit version and system, ready to paste into a bug report.

Usage: python3 <kit>/scripts/about.py
Prints no paths, keys or repo names.
"""
import json
import os
import pathlib
import platform
import shutil
import subprocess
import sys

KIT = pathlib.Path(__file__).resolve().parent.parent


def version():
    try:
        return json.loads((KIT / ".claude-plugin" / "plugin.json").read_text())["version"]
    except (OSError, ValueError, KeyError):
        return "unknown"


def claude_version():
    if not shutil.which("claude"):
        return "not installed"
    try:
        out = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=10).stdout
        return out.strip().split()[0] if out.strip() else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def report():
    via = "Claude Code" if os.environ.get("CLAUDECODE") else "plain scripts"
    system = f"{platform.system()} {platform.release()}, Python {platform.python_version()}, Claude Code {claude_version()}, run from {via}"
    return f"Kit version: {version()}\nSystem: {system}"


if __name__ == "__main__":
    print(report())
