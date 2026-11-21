# Finding: do turned-down bets reach the next brief? (INT-245)

Checked 20 Nov 2026, before the change.

## Where a rejection and its reason are stored

- `decide.py no "why"` (`scripts/decide.py`, the `no` branch) appends one line per offered option to `decisions.md`:
  `- <date> | <option> | rejected by owner: <reason>`.
- `loop_lib.items()` (`scripts/loop_lib.py`) reads those lines to show an option as Declined in the inbox.
- `scripts/mcp_server.py` `search_decisions` serves `decisions.md` read-only, so the line is searchable by phrase.
- `scripts/handoff.py` puts the last 10 `decisions.md` lines in the context pack.
- No lessons code reads rejections: there is no `lessons` file or parser for them in `scripts/`.

## Does the product-manager agent read them?

Only by instruction. `agents/product-manager.md` lists `decisions.md` in its Record input ("The owner's decisions and
reasons outrank your earlier memos") and says never to re-propose a title marked rejected. Nothing in code enforces
that, and nothing in the brief shows it happened. If the agent proposed a turned-down bet again, the brief listed it
like any other option, with no sign that the owner had already said no.

## Change

`loop_lib.morning()` now reads the same `rejected by owner:` lines. An option the owner already turned down is not
offered again, and the brief says so in one line with the date and reason. A bet the owner has since taken up (it has
a line in `bets.md`) is offered as normal.
