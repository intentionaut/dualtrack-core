#!/usr/bin/env python3
"""Once a day, at Claude Code session start, in the background: is each connected source's server up, and has its
tool list changed? One cheap call loads every connected source's server, and its start-up event answers both.

    source_health.py               check now, unless the last check is under a day old
    source_health.py --background  the same, detached, so the session starts at once (the plugin's SessionStart hook)
    source_health.py --force       check now

Writes <DUALTRACK_HOME or ~/.dualtrack>/source-health.md, one line per source. Nothing is ever changed: the loop shows
any line that is not ok in the brief, and the owner decides. A check that cannot run says so in the file.
"""
import datetime
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sources

HOME = pathlib.Path(os.environ.get("DUALTRACK_HOME") or pathlib.Path.home() / ".dualtrack")
OUT = HOME / "source-health.md"
DAY = 20 * 3600  # a little under a day, so a morning session always gets a fresh check


def connected():
    """Sources whose server this machine has added. A claude.ai connector has no entry here, so it is not checked."""
    return {n: c for n in sources.load() if (c := sources.mcp_config(n))}


def check(claude=None, today=None):
    today = today or datetime.date.today().isoformat()
    found = connected()
    if not found:
        return [f"- {today} | none | ok"]
    conf = {"mcpServers": {k: v for c in found.values() for k, v in c["mcpServers"].items()}}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:  # private: an entry can hold a key
        os.chmod(f.name, 0o600)
        json.dump(conf, f)
    try:
        r = subprocess.run([claude or os.environ.get("CLAUDE", "claude"), "-p", "Reply ok.", "--model", "haiku",
                            "--max-turns", "1", "--permission-mode", "dontAsk",
                            "--output-format", "stream-json", "--verbose", "--disable-slash-commands", "--setting-sources=",
                            "--strict-mcp-config", "--mcp-config", f.name],
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=180)
        init = next((e for e in sources.events(r.stdout.splitlines()) if e.get("subtype") == "init"), None)
    except (OSError, subprocess.TimeoutExpired) as e:
        init, r = None, e
    finally:
        os.unlink(f.name)
    if init is None:
        return [f"- {today} | check | could not run: {str(getattr(r, 'stderr', r) or 'no start-up event')[:120].strip()}"]
    # The check is a paid call too: its cost is shown with its result, never capped by the kit.
    done = next((e for e in sources.events(r.stdout.splitlines()) if e.get("type") == "result"), {})
    cost = done.get("total_cost_usd")
    # Its own line: the loop reads each source's line by name and its "| ok" ending.
    return [f"- {today} | {n} | {note}" for n in found for note in (sources.drift(n, init) or ["ok"])] + \
        [f"- {today} | check | cost ${cost}" if cost is not None else f"- {today} | check | cost unknown"]


def main(a):
    if "--background" in a:
        subprocess.Popen([sys.executable, os.path.abspath(__file__)], start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return 0
    if "--force" not in a and OUT.exists() and time.time() - OUT.stat().st_mtime < DAY:
        return 0
    HOME.mkdir(parents=True, exist_ok=True)
    OUT.write_text("# Source health\n\n" + "\n".join(check()) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
