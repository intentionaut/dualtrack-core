# Plan: locked areas and the safety card (INT-241), out-of-date checks (INT-242)

Free, one team. Scope is the Done lines only.

## Tests first (`tests/test_safety_card.py`)

1. Setup suggests locked areas from the repo's files, and saves the owner's choice as `**Locked area:**` lines in the profile.
2. A diff that touches a locked area stops with a plain message and three choices; a bet the owner allowed goes through.
3. The card shows Passed, Stopped and Not checked rows, each with one grey line, and ends with one outcome question.
4. No card or message asks the owner to read a diff.
5. Autonomy (Auto-merge) decides whether the card asks or only records. A stop always asks.
6. INT-242: a failing check that the run rewrites, then passes, shows "Not checked", never "Passed", with the old and new check side by side. A real failure shows "Stopped" with the reason.

## Files

- `scripts/safety_card.py` (new): suggest, save, check and render. One place for the logic.
- `scripts/setup_apply.py`: `--locked` saves the choice.
- `scripts/loop_lib.py`, `scripts/daily_loop.sh`: stop on a locked area (reuses `hold` and `decide allow`); the card joins the pull request text.
- `agents/engineer.md`: stop before editing a locked area; report `Checks:` in plain words.
- `skills/dualtrack-setup/SKILL.md`: the locked-areas step.
- `safety-files.json`: re-pinned.

## Shortcuts

- Areas are found by file path words, not by reading the code. Upgrade when a miss is reported.
- A check is "rewritten" when an existing test file it names lost lines in this run's diff.
- All copy is draft.
