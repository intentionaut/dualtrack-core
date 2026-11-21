#!/usr/bin/env python3
"""Read-only data sources: which MCP tools a source may call, and how to connect it.

    sources.py check                  every entry in sources.json is read-only and complete
    sources.py menu                   every source, grouped by kind, with what it reads
    sources.py names <profile>        the profile's Sources line, one known name per line
    sources.py tools <name>           the allowed tool names, mcp__<name>__<tool>, one per line
    sources.py ask <name> [profile]   what to ask that source; the whole backlog when the profile's Backlog line names it
    sources.py setup <name>           the command that connects it in Claude Code
    sources.py schema                 the JSON Schema the reader must answer in
    sources.py unpinned <name>        why this machine's local server is not the pinned version; exit 1 if so
    sources.py mcp-config <name>      the source's own server entry from Claude Code's config, as --mcp-config JSON; exit 1 if not added
    sources.py digest <name> <stream.jsonl>          the run's result JSON, with the tools it really called
    sources.py render <name> <today> <claude-json>   the reader's fields as Markdown; anything off-shape is dropped
"""
import json
import pathlib
import re
import profile_value  # noqa: E402
import sys

KIT = pathlib.Path(__file__).resolve().parent.parent
# A tool whose name holds one of these words could change the owner's data, so it may not be listed.
WRITE = {"create", "update", "delete", "set", "edit", "merge", "dismiss", "promote", "rename", "enable", "disable",
         "launch", "end", "roll", "link", "unlink", "bulk", "duplicate", "add", "remove", "send", "post", "patch",
         "transition", "watch", "manage", "write", "destructive", "upload", "execute", "move", "assign", "archive",
         "close", "reopen", "submit", "publish", "schedule", "invite", "upsert", "toggle", "react", "apply", "import", "recover", "restore", "start", "stop", "copy", "change", "undo", "mark", "save"}


# Setup offers sources in this order, one group per kind.
KINDS = {"analytics": "Analytics", "calls": "Calls and research", "support": "Support and feedback",
         "docs": "Docs", "tracker": "Tracker", "errors": "Errors"}


def menu():
    by = {k: [] for k in KINDS}
    for n, s in load().items():
        by[s["kind"]].append(f"- {n}: {s['reads']}")
    return "\n\n".join(f"{KINDS[k]}\n" + "\n".join(rows) for k, rows in by.items() if rows)


# A tool must also name a read: a list of write words can never be complete (createissue, snooze_alert, run_job).
READ = {"get", "list", "search", "query", "find", "read", "fetch", "view", "retrieve", "describe", "summarize", "aggregate",
        "analyze", "compare", "inspect", "check", "discover", "diff", "export", "download", "render", "filter", "ask",
        "overview", "details", "info", "insights"}
# Read tools whose names carry no read verb, each checked against the vendor's docs when it was added.
REVIEWED = {"acquisitionTrend", "agentAnalyticsKeyMetrics", "appUsage", "appUsageTimeSeries", "cohortRetentionCurve", "entityUsage",
            "entityUsageTimeSeries", "execute_sql_readonly", "exp_program_reporting_top_experiments", "guideEffectivenessMetrics",
            "productEngagementScore", "resolveConfluenceContentMacros", "surveyResponses", "surveyScores", "use_amplitude_ai_feedback"}


def load():
    return json.loads((KIT / "sources.json").read_text())


def words(tool):
    return {w.lower() for w in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])", tool)}


def writes(tool):
    """The write words in a tool's name. A vendor's own "readonly" excuses "execute" only: execute_sql_readonly runs SELECT."""
    found = words(tool) & WRITE
    return found - {"execute"} if "readonly" in words(tool) else found


def problems(name, s):
    # A Claude.ai connector has no URL here: the owner connects it at claude.ai, and its tools carry its own prefix.
    # A local (stdio) server has a command instead, and says how to add it.
    out = [] if s.get("url", "").startswith("https://") or s.get("server", "").startswith("claude_ai_") or \
        (s.get("command") and s.get("connect")) else [f"{name}: url is not https"]
    if not s.get("tools"): out.append(f"{name}: no tools")
    # A server run on this machine is pinned: "latest" changes its tools and their text under the owner, unreviewed.
    if s.get("command") and not (s.get("pin") and s["pin"] in s["command"] and s["pin"] in s.get("connect", "")):
        out.append(f"{name}: a local server needs a pinned version in command and connect")
    # Every tool on a server is allowed only where the vendor enforces read-only, at a /readonly endpoint.
    if s.get("tools") == ["*"] and not s.get("url", "").rstrip("/").endswith("/readonly"):
        out.append(f"{name}: all tools are allowed only on a vendor read-only endpoint")
    if not s.get("ask"): out.append(f"{name}: no ask")
    if s.get("kind") not in KINDS: out.append(f"{name}: kind is not one of {', '.join(KINDS)}")
    if not s.get("reads"): out.append(f"{name}: no reads line")
    out += [f"{name}: {t} looks like a write tool" for t in s.get("tools", []) if t != "*" and writes(t)]
    out += [f"{name}: {t} names no read, so it may not be listed" for t in s.get("tools", [])
            if t != "*" and not writes(t) and not words(t) & READ and t not in REVIEWED]
    return out


# The reader is quarantined: it sees the source's raw text, but only these fields leave it, and the kit checks
# each one. Short one-line plain text, a real number, a tool it was given: no room for prose or orders.
TEXT = re.compile(r"[A-Za-z0-9 .,%/()_:+~-]{1,60}")
FIELDS = ("measure", "unit", "tool", "query", "range")
SCHEMA = {"type": "object", "required": ["findings", "unread", "planted"], "additionalProperties": False, "properties": {
    "findings": {"type": "array", "maxItems": 20, "items": {"type": "object", "additionalProperties": False,
                 "required": ["measure", "value", "unit", "tool", "query", "range"],
                 "properties": {**{f: {"type": "string", "maxLength": 60} for f in FIELDS}, "value": {"type": "number"},
                                "rows": {"type": "integer", "minimum": 0}}}},
    "unread": {"type": "array", "maxItems": 20, "items": {"type": "object", "additionalProperties": False, "required": ["tool", "reason"],
               "properties": {"tool": {"type": "string", "maxLength": 60}, "reason": {"type": "string", "maxLength": 60}}}},
    "planted": {"type": "integer", "minimum": 0}}}


def clean(v):
    """One field, or None. Home folders are masked; anything else off-shape drops the item."""
    v = re.sub(r"/(Users|home)/[^/ ]+", "/~", str(v)).strip()
    return v if TEXT.fullmatch(v) else None


def mcp_config(name, home=None, cwd=None):
    """The one server this source needs, as Claude Code stored it (user or local scope), or None. The repo's own
    .mcp.json is never read: a pull request can add it, and it would set the server command.
    Agents run with --setting-sources= so the machine's own setup stays out; that also drops servers added
    with claude mcp add, so the reader gets its own server back by name, and nothing else."""
    import os
    server = load()[name].get("server", name)
    home = home or os.environ.get("DUALTRACK_MCP_HOME") or os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~")
    cwd = cwd or os.getcwd()
    found = []
    try:
        conf = json.loads(pathlib.Path(home, ".claude.json").read_text())
        found += [conf.get("projects", {}).get(cwd, {}).get("mcpServers", {}), conf.get("mcpServers", {})]
    except (OSError, ValueError):
        pass
    entry = next((f[server] for f in found if server in f), None)
    return {"mcpServers": {server: entry}} if entry else None


def unpinned(name, entry):
    """Why this machine's server for a local source is not the pinned version, or "" when it is (or is not local)."""
    pin = load()[name].get("pin")
    if not pin or not entry:
        return ""
    run = " ".join([entry.get("command", "")] + entry.get("args", []))
    # Exact runner and one whole pin argument, nothing else: substring checks let `sh -c "... # pin"` or `uvx pin --x` pass.
    return "" if [entry.get("command")] + entry.get("args", []) == load()[name]["command"].split() else f"{name} runs `{run.strip()}`, not the pinned {pin}: run {load()[name]['connect']}"


def prefixes(name):
    s = load()[name]
    return [f"mcp__{n}__" for n in [s.get("server", name)] + ([s["connector"]] if s.get("connector") else [])]


def short(name, tool):
    """A full MCP tool name as the source's own short name, or None if it is another server's."""
    return next((tool[len(p):] for p in prefixes(name) if tool.startswith(p)), None)


def drift(name, init):
    """From a session's start-up event: the source's server status, listed tools it no longer offers, and new
    read-looking ones. Notes only; nothing is changed."""
    s = load()[name]
    status = [m.get("status") for m in init.get("mcp_servers", []) if m.get("name") in (s.get("server", name), s.get("connector"))]
    if not status:
        return ["not connected"]
    if "connected" not in status:
        return [f"{status[0]}: connect it with {main_setup(name)}"]
    offered = {x for x in (short(name, t) for t in init.get("tools", [])) if x}
    if not offered or s["tools"] == ["*"]:
        return []
    gone = [t for t in s["tools"] if t not in offered]
    # left_out names tools passed over on purpose, so only a real change is flagged.
    new = sorted(t for t in offered - set(s["tools"]) - set(s.get("left_out", [])) if not writes(t))
    return [f"gone: {', '.join(gone)}"] * bool(gone) + [f"new, read-looking: {', '.join(new)}"] * bool(new)


def main_setup(name):
    s = load()[name]
    return s["connect"] if s.get("connect") else f"claude mcp add --transport http {name} '{s['url']}'"


def events(lines):
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue  # a torn line is skipped, never fatal
    return out


def digest(name, lines):
    """From claude's stream-json: the result event, with the source's tools the reader really called."""
    ev = events(lines)
    result = next((e for e in reversed(ev) if e.get("type") == "result"), None)
    if result is None:
        raise ValueError("no result in the reader's output")
    result["dualtrack_calls"] = sorted({x for e in ev if e.get("type") == "assistant" for c in e.get("message", {}).get("content", [])
                                        if c.get("type") == "tool_use" and (x := short(name, c["name"]))})
    return result


def fields(out):
    """A reader's checked-schema answer from claude's JSON: structured_output, or JSON in result. {} if neither."""
    j = json.loads(out)
    try:
        data = j.get("structured_output") or json.loads(j.get("result") or "")
    except ValueError:
        data = {}
    return data if isinstance(data, dict) else {}


def render(name, today, out):
    """Markdown built only from checked fields, and what was dropped. The reader's own prose never gets through."""
    s, data = load()[name], fields(out)
    # The tools the reader really called, when the run recorded them; else the source's list.
    called = json.loads(out).get("dualtrack_calls")
    tools, dropped, lines, unnamed = set(called if called is not None else s["tools"]), 0, [], set()
    for f in data.get("findings", [])[:20]:
        got = {k: clean(f.get(k, "")) for k in FIELDS} if isinstance(f, dict) else {}
        ok = got and all(got.values()) and isinstance(f.get("value"), (int, float)) and not isinstance(f.get("value"), bool)
        if not ok:
            dropped += 1
            continue
        # The allowlist already limited what it could call, so a tool name off the list is a label to fix, not a risk:
        # the number is kept, marked, and the name is reported so the list can be corrected.
        tool = got["tool"]
        # Optional: older readers send no row count, and their numbers still count.
        rows = f", {f['rows']} rows" if type(f.get("rows")) is int and f["rows"] >= 0 else ""
        if called is None and "*" in tools:
            pass
        elif tool not in tools:
            unnamed.add(tool); tool = f"unlisted tool: {tool}"
        lines.append(f"- {got['measure']}: {f['value']:g}{'' if got['unit'] == '-' else got['unit'] if got['unit'] == '%' else ' ' + got['unit']} ({tool}, {got['query']}, {got['range']}{rows})")
    # A failure is never hidden: an off-shape reason still names the tool.
    unread = [f"- {t}, {clean(u.get('reason', '')) or 'could not be read'}" for u in data.get("unread", [])[:20]
              if isinstance(u, dict) and (t := clean(u.get("tool", "")))]
    planted = data.get("planted") if type(data.get("planted")) is int else 0
    md = f"# Source: {name}, {today}\n\n" + ("\n".join(lines) or "- none found") + "\n\nCould not be read:\n" + ("\n".join(unread) or "- none") + "\n"
    return md, dropped, planted, sorted(unnamed)


def ask(name, profile=None):
    """The source's ask, or its backlog-wide ask when the profile's Backlog line is "<name>: <project>"."""
    s = load()[name]
    source, _, project = (profile_value.field(pathlib.Path(profile).read_text(), "Backlog") if profile else "").partition(":")
    if source.strip().lower() != name or not s.get("backlog_ask"):
        return s["ask"]
    # The project name goes into the reader's prompt: a short plain name only, never a sentence that could give orders.
    if not re.fullmatch(r"[A-Za-z0-9 _-]{1,40}", project.strip()):
        sys.exit(f"Backlog: the project name must be 1 to 40 letters, digits, spaces, _ or -: {project.strip()[:40]}")
    return s["backlog_ask"].replace("{project}", project.strip())


def names(profile):
    value = profile_value.field(pathlib.Path(profile).read_text(), "Sources")
    if not value or value.startswith("<") or value.lower() in ("none", "unknown"):
        return []
    known, out = load(), []
    for n in (p.strip().lower() for p in value.split(",") if p.strip()):
        if n not in known:
            sys.exit(f"unknown source: {n}; known: {', '.join(known)}")
        out.append(n)
    return out


def main(a):
    if a[:1] == ["check"]:
        bad = [p for n, s in load().items() for p in problems(n, s)]
        print("\n".join(bad) or "checked: every source is read-only")
        return 1 if bad else 0
    if a[:1] == ["mcp-config"] and len(a) == 2 and a[1] in load():
        c = mcp_config(a[1])
        if c is None:
            return 1
        print(json.dumps(c))
        return 0
    if a[:1] == ["unpinned"] and len(a) == 2 and a[1] in load():
        why = unpinned(a[1], ((mcp_config(a[1]) or {}).get("mcpServers") or {None: None}).popitem()[1])
        print(why)
        return 1 if why else 0
    if a[:1] == ["digest"] and len(a) == 3 and a[1] in load():
        try:
            print(json.dumps(digest(a[1], pathlib.Path(a[2]).read_text().splitlines())))
        except (OSError, ValueError) as e:
            print(f"could not read the reader's output: {e}", file=sys.stderr)
            return 1
        return 0
    if a[:1] == ["menu"]:
        print(menu())
        return 0
    if a[:1] == ["schema"]:
        print(json.dumps(SCHEMA))
        return 0
    if a[:1] == ["render"] and len(a) == 4 and a[1] in load():
        md, dropped, planted, unnamed = render(a[1], a[2], pathlib.Path(a[3]).read_text())
        print(md, end="")
        print(f"{dropped} {planted} {';'.join(unnamed)}", file=sys.stderr)
        return 0
    if a[:1] == ["names"]:
        print("\n".join(names(a[1])))
        return 0
    s = load().get(a[1]) if len(a) == 2 or a[:1] == ["ask"] and len(a) == 3 else None
    if s is None or problems(a[1], s):
        sys.exit(f"unknown or unsafe source: {' '.join(a[1:])}")
    if a[0] == "tools":
        # The same read tools under each name the server can have: added with claude mcp add, or as a Claude.ai connector.
        for server in [s.get("server", a[1])] + ([s["connector"]] if s.get("connector") else []):
            print("\n".join(f"mcp__{server}" if t == "*" else f"mcp__{server}__{t}" for t in s["tools"]))
    elif a[0] == "ask":
        print(ask(a[1], a[2] if len(a) == 3 else None))
    elif a[0] == "setup":
        print(main_setup(a[1]))
    else:
        sys.exit(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
