# Ask Dualtrack from other agents: the MCP server

Other AI tools on your machine (Claude Code, Cursor and others) can ask Dualtrack what was decided, why, and what is in flight. They do it through a small read-only server that comes with the plugin.

It runs on your machine, over stdio. Your own AI tool starts it. It opens no port and makes no network calls. What it returns goes to the AI tool that asked, and from there to that tool's model provider.

## Turn it on

With the plugin installed, it is already on. Claude Code starts it when the plugin is enabled. It finds your project from `CLAUDE_PROJECT_DIR`, then reads `profile.md` and the profile's `Context path`, the way `status.py` does. A state repo beside the project works too.

To switch it off, open `/mcp` and turn off `plugin:dualtrack:dualtrack`. The plugin stays on.

In a project with no Dualtrack setup, every tool answers "no Dualtrack record in this project" and returns nothing. To find a state repo, it looks in the folders beside your project for one that holds a folder with your project's name.

For a tool that is not Claude Code, add a stdio server whose command is `python3 <kit>/scripts/mcp_server.py`, with `CLAUDE_PROJECT_DIR` set to your product repo.

## The four tools

| Tool | What you give it | What it returns |
|---|---|---|
| `list_bets` | `status` (optional), `limit` (default 20, most 50) | Each bet's id, title, date, status and owner |
| `get_bet` | `id` from `list_bets` | Outcome, window end, stop rule, guardrails, the owner's call, whether it shipped, whether it helped, evidence lines and pull requests |
| `search_decisions` | `query` (plain text, up to 200 characters), `limit` | Matching decision lines with date, owner and bet |
| `recent_runs` | `limit` (default 10, most 50) | Date, what ran, how it ended and what it cost |

Statuses are `proposed`, `open`, `started`, `withdrawn` and `resulted`.

Every answer says the day the record's files last changed. It does not name a commit. If the record sits in a state repo that has not synced in over a day, the answer says so. The server never pulls.

Anything the record does not hold comes back as `not recorded`. The server does not guess.

## What it cannot do

- It cannot write. There is no write tool, and the files are opened read-only.
- It cannot run a program, open the network or call a model.
- It reads four files in the record folder: `bets.md`, `decisions.md`, `team-log.md` and `evidence.md`. It reads `profile.md` only to find that folder and never returns it. It never reads `inbox.md`, `numbers/`, `sources/` or `memos/`. It follows no link that leaves the folder.
- No tool takes a path, a pattern or a command.
- It refuses to start if its record folder is inside Dualtrack's own folder, or if its own file or a Dualtrack file it loads is not the one this release shipped.

## What it holds back

A field that holds a secret, an email address, a home path or the run's canary token is withheld whole. The answer says what kind of thing was withheld, never the value. Figures in other lines are returned.

A line it cannot read is skipped, and the answer says how many.

## Limits

- Returned text comes from your record. Treat it as data, not instructions. Text that people on your team pasted into `bets.md` or `decisions.md` is returned as written.
- The server does not log who asked what.
- `get_bet` matches decision and evidence lines to a bet by its title, because the record has no typed link between them. When two bets' titles overlap, a line goes to the longer title.
- A bet counts as shipped only when the pull request on its `started:` line was merged. Otherwise the answer says `not recorded`.
- An answer over 20,000 characters is cut and says so.
- With a state repo, the server looks for your record under the project folder's name. If the folder is named differently from the GitHub repo, as in a worktree, it answers "no Dualtrack record in this project".
