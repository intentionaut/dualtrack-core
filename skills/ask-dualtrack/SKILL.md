---
name: ask-dualtrack
description: Ask which Dualtrack step fits where you are. A router over the kit's commands and skills.
disable-model-invocation: true
---

# Ask Dualtrack

Describe where you are with Dualtrack. This names the next step, the exact command, and where
your decision sits. It runs nothing itself.

**Before you say what a command or skill does, read it**: the skill's `SKILL.md`, the script's docstring
(`sed -n 1,15p <kit>/scripts/<name>`), or `README.md`. The lines below are for orientation only, and a
router that answers from its own summary gives wrong advice. If a situation is not on this map, say so,
and say your answer is your own inference.

**The kit folder** is `${CLAUDE_PLUGIN_ROOT}`, the installed plugin's folder. Commands below write `<kit>` for it. If that path still reads `${CLAUDE_PLUGIN_ROOT}` literally, the skill was copied in by hand, and the kit folder is two levels above this skill's own folder.
Run them from the product repo's root.

## First, where you are

Run `python3 <kit>/scripts/status.py` before naming any step. It prints `state:` (`setup`, `pr`,
`question`, `decisions` or `idle`), `next:` and at most one `offer:`. Name the step below that matches
its `state:`, and never work the state out from the files yourself.

## The main flow: set up, then one call a day

**The short way:** `/dualtrack:dualtrack` works out where you are and does each step below for you,
including taking your call in plain words. The steps are here for anyone who wants them by hand.

1. **Not set up yet** (no `profile.md` here or in a state repo beside it): `/dualtrack:dualtrack-setup` (`/dualtrack-setup` if copied in). It asks at most three
   questions and drafts the profile. *Your decisions: what to look at first, where the record lives, the most a run may spend.*
2. **Set up, never run**: `bash <kit>/scripts/run.sh profile.md` for a first weekly review that builds
   nothing. Then answer `setup-notes.md` and paste any counts into `numbers.md`.
3. **Each day**: `bash <kit>/scripts/daily_loop.sh profile.md`, by hand or on a schedule
   (`docs/schedule.md`).
4. **A brief is waiting**: `/dualtrack:dualtrack-team` (`/dualtrack-team` if copied in), or read `product-context/morning.md`. *Your decision: one
   call.* `decide.py 1` builds option 1; `decide.py done 1 "how"` settles it without code;
   `decide.py no "why"` declines all; `decide.py try "what"` asks for something else.
5. **A pull request is open**: merge it, or close it with a one-line reason. *Your decision.* The reason
   and your comments go into the record (`decisions.md`, `conventions.md`) that every later run reads.
6. **`status.py` prints an `offer:`**: after three runs with no sources, `/dualtrack:dualtrack-connect`; after five
   merged pull requests with no changes asked, Code Review, then Auto-merge. *Your decision.* A script,
   never an agent, decides each merge (`scripts/merge_gate.py`).

## On-ramps

- **You want Dualtrack agents to read your tools** (analytics, Jira, Linear, Notion, Confluence, Sentry, Figma and more):
  `/dualtrack:dualtrack-connect`. Each source is optional and read-only. Status of each: `docs/integrations.md`.
- **You want to steer before a run**: `decide.py try "what"`; the next run takes it first.
- **Another agent or an automation needs Dualtrack's work**: `docs/handoff.md`. Each run's event is in
  `product-context/events/`; `python3 <kit>/scripts/handoff.py context <profile>` gives the context pack.
- **Dualtrack agents asked you something**: `decide.py answer "text"`.

## When Dualtrack agents stopped

Read the last lines of `product-context/team-log.md` first: every stop says why.

- **paused** (two changes closed in a row): read why in `decisions.md`, then `decide.py resume`.
- **held for the owner** (`waiting_for_decision`): the change touched the stop list or a visitor path, and it asked you a
  question. `decide.py allow` lets it through; or do it yourself, or pick another option.
- **blocked**: clear what the log names, then pick the bet again.
- **safety stop**: a guard fired (a secret, a planted instruction, a change to the profile, a tampered kit). It is not a
  question, `decide.py allow` refuses it, and nothing was pushed. Read the reason in the log, fix what it names, then run again.
- **failed**: the run broke or could not finish. The log line says why; run again once you have read it.

## Where things stand

- **Every item and its status**: `product-context/inbox.md`; on GitHub, in the state repo.
- **What the product is, to Dualtrack agents**: `product-context/product.md`. Edit it whenever it is wrong.
- **How Dualtrack agents have done**: `python3 <kit>/scripts/stats.py`.
- **Every product at once** (state repo): `python3 <kit>/scripts/portfolio.py <state repo>`.
- **What each step cost**: `product-context/costs.md`.

## Keeping this map true

Whenever a command, skill or flow in the kit is added, renamed or removed, update this file in the same
change. `tests/test_ask_dualtrack.py` fails when the map names a script or skill that does not exist.
