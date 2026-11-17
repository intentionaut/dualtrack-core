---
name: dualtrack-connect
description: Connect Dualtrack to the tools a team already uses (analytics, trackers, docs, feedback, errors, design) as optional read-only sources. Lists every source the kit supports, connects the ones the owner picks, signs in once, and adds them to the profile's Sources line. Use when the user says "connect", "add a source", "connect Jira", "use our analytics", or asks which tools Dualtrack can read.
---

# Connect a source

Every source is optional and read-only. Dualtrack agents read it for evidence; they never write to it. Ask in
plain sentences, one thing at a time.

**The kit folder** is `${CLAUDE_PLUGIN_ROOT}`. Commands below write `<kit>` for it. If that path still
reads `${CLAUDE_PLUGIN_ROOT}` literally, the kit folder is two levels above this skill's own folder.

## 1. Show what is available

Read `<kit>/sources.json` and `<kit>/docs/integrations.md` (its status table). Show one short table:
source, what Dualtrack agents would learn from it (from its `ask`), and state: built or waiting, with the reason.
Read the profile's **Sources** line and mark the ones already on. Ask which to add. Recommend at most
two, from what the product is (the profile's **Product** and **Goal**).

## 2. Connect each one the owner picks

For each:

1. Run `python3 <kit>/scripts/sources.py setup <name>` and show the line it prints.
   - A `claude mcp add ...` line: say it adds the server to their Claude Code, then run it.
   - A "Connect ... at claude.ai" line: give them that link; they do it in the browser.
2. Read the source's `note` from `sources.json` aloud, in plain words. It says what an admin must allow,
   which write tools to switch off on the vendor's side, and what is left out because it is personal data.
3. Sign in once, so scheduled runs can use it: they type `! claude mcp login <name>` and follow the
   browser prompt. A scheduled run cannot sign in by itself.
4. Check it: `python3 <kit>/scripts/sources.py tools <name>` lists the only tools Dualtrack agents may call.

## 3. Turn it on

Add the name to the profile's **Sources** line, comma-separated, keeping what is there. This is the one
profile line this skill may change; show the line before and after. Then say the next run reads it before
research, writes what it found to `<context>/sources/<name>.md`, and cites it in the brief. A source that
fails says it could not be read; it never reads as "no data".

## Rules

- Never add a tool to `sources.json` here. A new source or tool goes through a pull request, with its tool
  names checked against the vendor's docs and `python3 <kit>/scripts/sources.py check` passing.
- Never ask for, show or store a password, token or key. Sign-in happens in the vendor's own page.
- Company mode, or an API-key login: Claude.ai connectors (such as Google Drive) do not reach the run. Say so.
