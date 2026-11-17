---
name: dualtrack-team
description: Dualtrack's morning brief. Shows what Dualtrack agents did and today's decisions as a table (change, reason, expected outcome), asks for your call, and records it. Use when the user says "morning brief", "what does my team say", "product team", or asks what to decide today.
---

# Product team

Dualtrack agents run on their own and leaves a brief. Your job here is to put it in front of the
owner, get one decision, and record it. You never build, merge or edit the record by hand.

1. **Find the brief.** The profile is `profile.md` in the current folder, or, with a
   state repo, `../<state repo>/<this folder's name>/profile.md`. Read its **Context
   path** (default `./product-context`), then read `<context>/morning.md`. If there is
   no profile, offer `/dualtrack:dualtrack-setup`. If there is no brief, say so and offer to run
   Dualtrack agents now: `bash <kit>/scripts/daily_loop.sh <profile>`, where `<kit>` is
   `${CLAUDE_PLUGIN_ROOT}` (two levels above this skill's folder if that reads literally). Say that a run takes a few minutes and uses the
   owner's Claude plan. With a state repo, `git -C <state repo> pull` first, so a cloud
   run's brief is there.
2. **Show it as it is.** What Dualtrack agents did, the next step, the Decisions table
   exactly as written, and the question if there is one. Add nothing and rank nothing.
   If a pull request is linked, give its link.
3. **Ask for one input**, in plain words:
   - a number, to build that option
   - "none", with a reason
   - something else they want instead
   - an answer to the question
4. **Record it** with the command the brief gives, `python3 <kit>/scripts/decide.py`:
   `1`, `no "why"`, `try "what"`, `answer "text"` or `resume`. Show what it printed.
5. **Say what happens next:** the next run takes the choice first. A visible change
   comes back as a pull request for review. Nothing merges without the owner, unless the
   profile turns **Auto-merge** on and every check in `scripts/merge_gate.py` holds.

If the owner asks why an option is there, read the dated memo in `<context>/memos/`
and quote its reasons with their sources. Do not invent a reason the memo does not give.
