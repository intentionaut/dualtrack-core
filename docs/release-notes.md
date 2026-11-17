# Release notes

The default for every release note the kit or its team writes: brief, clear, and
readable by an agent that has seen nothing else. `loop_lib.py notes <file>` checks a
file against these rules. The loop holds any change whose release notes fail.

## Shape

```
## <version> - <YYYY-MM-DD>

Changed:
- <imperative line: what now behaves differently>

Breaking:
- <what stops working, and the one step that fixes it> | none

Upgrade:
- <exact command or file edit> | none

Check:
- <one command or observation that shows the release works>
```

- One section per release, newest first.
- Each line says one thing, in under 25 words. No more than ten Changed lines; group the rest.
- Name files, commands, flags and profile fields exactly, in backticks.
- Write for a reader who will act on it: no story, no thanks, no reasons beyond one clause.

## Never include

- Secrets: keys, tokens, passwords, connection strings, or any value from `.env` files.
- Personal data: email addresses, phone numbers, home paths such as `/Users/<name>/`.
- Private numbers: revenue, user counts, costs or prices for a named product, unless the owner published them.
- Chat logs: transcripts, agent or user turns, "I'll", "Let me", tool output, session or run IDs.
- Branch names of team runs, stopped runs, and the reviewer's back-and-forth.
- Anything from `decisions.md`, `bets.md` or memos beyond the change itself.

Where a fact is needed but private, write what changed for the reader and leave the
fact out.
