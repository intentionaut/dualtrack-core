# Notion option

This has not been tested on a live workspace. Try it on a test page first.

Your record stays in local Markdown files. Notion is a copy, so a failed sync loses nothing.

1. Connect the Notion connector in Claude Code.
2. Set `**Context store:** notion`, a local `**Context path:**`, and `**Notion page:**`.
3. Under that page, make a database called Decisions with properties Date, Decision, Answer and Reason.
4. File each run as usual with `scripts/file_memo.py`.
5. Run the sync in `prompts/notion-sync.md`.

Writes go one way, local to Notion. Decisions are the exception: your Answer and Reason are read back into `decisions.md` before each run, so you can decide from anywhere.

If Notion cannot be reached, the sync reports `notion: unknown` and the local files stand. That result never means nothing changed.
