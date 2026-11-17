# Run Dualtrack agents every day

There are two ways to run Dualtrack agents every day. Pick one. Both run on your own Claude plan.

| | In the cloud | On this computer |
|---|---|---|
| Runs when your laptop is closed | Yes | No |
| Your code and record are processed in | Anthropic's cloud | your computer |
| The brief appears in a Claude doc | Not yet: it stays in files in your state repo | Yes, if **Brief doc** is `claude` |
| Where the record lives | A private state repo, which the cloud run reads and writes | Anywhere: a folder kept out of git, or a state repo |
| What you set up | One routine, at claude.ai/code/routines | One Claude Code session left open |

Anthropic's terms let each person run Dualtrack agents on their own Claude subscription only. Never set it up so that it runs on your plan for somebody else.

## In the cloud: a routine

A routine starts a fresh Claude Code session in Anthropic's cloud on a schedule. It clones your repos, runs the loop, and stops.

1. Keep the record in a private state repo. Setup does this when you choose it. A cloud run has no other place to read the record from.
2. In Claude Code, type `/schedule`. Then paste the request below. Fill in the three repos and the time. Your Dualtrack state is the repo dualtrack-state unless you named it at setup.

```text
Create a routine called "Dualtrack: <your repo>".
Run every day at 06:30 Europe/London.
Repositories: https://github.com/<you>/<your repo>, https://github.com/<the Dualtrack repo you installed from>, https://github.com/<you>/<your Dualtrack state>
Model: claude-sonnet-5-5. Tools: Bash, Read, Write, Edit, Glob, Grep. Connectors: none.
Prompt:
  cd into the <your repo> checkout. If git has no user.name, set user.name "Dualtrack" and user.email "dualtrack@users.noreply.github.com" for this checkout and the <your Dualtrack state> checkout.
  Run: bash ../dualtrack/scripts/daily_loop.sh ../<your Dualtrack state>/<your repo>/profile.md
  Report the last line it printed, word for word. Change nothing else.
```

3. Before the first run, open the routine at claude.ai/code/routines and remove every connector, such as email, files or calendar. A routine can get all of your connectors by default, and Dualtrack agents need none of them.
4. On the first day, check the routine's run at claude.ai/code/routines. The last line says what Dualtrack agents did, such as `opened: ...` or `quiet: ...`.

What we found when we tested the cloud on 4 November 2026:

- The repos are cloned side by side, so `../dualtrack` and `../<your Dualtrack state>` resolve.
- The loop's own `claude -p` calls work inside the cloud session.
- GitHub works over its REST API only. The kit uses REST throughout (`scripts/ghrest.py`).
- Pushing a `team/` branch works. Deleting a branch does not work, and the kit never deletes one.
- The Claude-Docs connector is not available inside the run, so set **Brief doc:** `none`. Setup does this for you.
- A run starts about a minute after its scheduled time.
- Delete a routine at claude.ai/code/routines. It cannot be deleted from inside Claude Code.

## On this computer: a session kept open

1. Open Claude Code in your repo, and leave the window open.
2. Type:

```text
/loop 24h Run bash ../dualtrack/scripts/daily_loop.sh profile.md and report the last line it printed.
```

With Dualtrack state in its own repo, use `../<your Dualtrack state>/<your repo>/profile.md` as the profile path.

Not yet tested over a full day. The run happens only while the session is open and the computer is awake. If you close it, start the loop again the next time you open Claude Code. If you would rather use your computer's own scheduler, such as cron, it runs the same command.

## What a run's exit code means

Every run ends in one of five states. A non-zero exit code means the run failed, was blocked or hit a safety stop. Waiting for your decision exits 0, like a finished run, so a scheduler should route on `gate_state`, not on the exit code alone.
The same word appears in the event (`gate_state`), the morning brief, `status.py` and the dashboard.

| State | Exit code | Meaning |
|---|---|---|
| `pass` | 0 | Finished. Nothing to do. |
| `failed` | 1 | It broke or could not finish. Read the reason, then run again. |
| `waiting_for_decision` | 0 | Only you can move it: a question, an open pull request, a pick. |
| `blocked` | 4 | It cannot go on until something on this machine or in the profile is fixed. Nobody is asked. |
| `safety_stop` | 5 | A safety check fired. It is never a question, and `decide.py allow` refuses it. |

Codes 2, 124 and 143 are not used by this table. Runs from before this table ended on 0, 1 or 2 in the same places.

## Either way

- Read the brief and make your call with `/dualtrack:dualtrack-team`, or in the brief doc.
- With a state repo, your call is pushed for you, so the next cloud run sees it.
- Dualtrack opens ready pull requests. **Auto-merge** is off by default; with it on, changes of up to 50 lines in up to 3 files that pass every check merge on their own (see the README).
- Code Review reads pull requests over REST, so it can run in cloud routines too (untested there). A failed review is never a pass: the change then waits for you.
