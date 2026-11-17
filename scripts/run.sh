#!/bin/bash
# One product manager run, with the handoffs done for you. Builds nothing.
#
# Usage: bash scripts/run.sh <profile.md> [weekly|daily]
# Env:   COST_CAP (default: the profile's Run cap, then none), CLAUDE.
set -uo pipefail
export PYTHONDONTWRITEBYTECODE=1  # a run leaves no .pyc beside the kit, so verify.py can flag any it finds

KIT=$(cd "$(dirname "$0")/.." && pwd)
PROFILE=$(cd "$(dirname "${1:?usage: run.sh <profile.md> [weekly|daily]}")" && pwd)/$(basename "$1")
# Profile paths are relative to the product repo's root, wherever in it the run starts.
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" || exit 1
CADENCE=${2:-weekly}; CLAUDE=${CLAUDE:-claude}; TODAY=$(date +%F); RUN=$(mktemp -d); SPENT=0
LIB="python3 $KIT/scripts/loop_lib.py"
. "$KIT/scripts/guards.sh"  # the same refusals as the daily loop
# Relative paths in the profile are relative to the product repo, where this runs, as in the daily loop.

# One reader for every script: profile_value.py drops the notes setup writes beside a value.
field() { python3 "$KIT/scripts/profile_value.py" "$PROFILE" "$1"; }
route() { local m; m=$(field Routing | tr ',' '\n' | sed -n "s/^ *$1 //p"); echo "${m:-$2}"; }
CAP=${COST_CAP:-$(field "Run cap")}; CAP=${CAP:-none}; CAP_SET=$CAP; case $CAP in none|off|no) CAP=100000 ;; esac
CONTEXT=$(field "Context path"); NUMBERS=$(field "Numbers file"); REPO=$(field Repo)
[ -n "$CONTEXT" ] || { echo "unknown: the profile needs Context path"; exit 4; }
mkdir -p "$CONTEXT"
# One run at a time per record: two at once would race to save it. A lock left by a run that died is taken over.
LOCK=${TMPDIR:-/tmp}/dualtrack-$(cd "$CONTEXT" && pwd -P | cksum | cut -d' ' -f1).lock
if ! mkdir "$LOCK" 2>/dev/null; then
  kill -0 "$(cat "$LOCK/pid" 2>/dev/null)" 2>/dev/null && { echo "stopped: another run is going for this record"; exit 4; }
  # The takeover runs under its own mutex, so two runs seeing the same dead pid cannot each delete the other's fresh lock.
  # shortcut: a run that dies holding the mutex is cleared after a minute (-mmin is whole minutes), by a rm that can itself race.
  [ -z "$(find "$LOCK.take" -maxdepth 0 -mmin +1 2>/dev/null)" ] || rm -rf "$LOCK.take"
  mkdir "$LOCK.take" 2>/dev/null || { echo "stopped: another run is taking over the run lock"; exit 4; }
  [ -z "${DUALTRACK_TEST_PAUSE_TAKEOVER:-}" ] || sleep "$DUALTRACK_TEST_PAUSE_TAKEOVER"  # test hook: widen the gap between check and takeover
  if kill -0 "$(cat "$LOCK/pid" 2>/dev/null)" 2>/dev/null; then rmdir "$LOCK.take"; echo "stopped: another run is going for this record"; exit 4; fi
  rm -rf "$LOCK"; mkdir "$LOCK" && echo $$ > "$LOCK/pid"; ok=$?; rmdir "$LOCK.take"
  [ $ok = 0 ] || { echo "stopped: could not take the run lock $LOCK"; exit 4; }
fi
# Every exit leaves one team-log line: a stop, a cap or a kill that nobody logged still says "stopped early" with its spend.
log_stop() { LOGGED=1; echo "- $TODAY | stopped early, $1 | \$$SPENT" >> "$CONTEXT/team-log.md"; }
echo $$ > "$LOCK/pid"; trap '[ -n "${LOGGED:-}" ] || log_stop "run ended before it finished"; rm -rf "$LOCK"; [ -z "${SAFE:-}" ] || exit 5' EXIT  # a safety stop ends the run with its code, whatever came after
trap 'exit 143' TERM INT
# What is already built, joined per open issue, so no step proposes work that shipped (worklog.py).
WORK=$CONTEXT/work.json; python3 "$KIT/scripts/worklog.py" --repo "${REPO:-.}" --out "$WORK" || WORK=none
SHARED="Moves file: $KIT/moves.md. Today is $TODAY. Profile: $PROFILE. Numbers: $NUMBERS. Repo: ${REPO:-none}. Work: $WORK."

# ask <step> <model> <prompt> <tools...>; the result goes to $RUN/<step>.txt
ask() {
  local step=$1 model=$2 prompt=$3 agent=product-manager; shift 3
  [ "$step" = ux ] && agent=ux-review
  "${AGENT_LIMIT[@]}" "$CLAUDE" -p "$prompt" --append-system-prompt-file "$KIT/agents/$agent.md" --model "$model" $LEAN \
    --max-budget-usd "$(python3 -c 'import sys; print(max(float(sys.argv[1]) - float(sys.argv[2]), 0.01))' "$CAP" "$SPENT")" \
    --permission-mode dontAsk --output-format json --allowedTools "$@" --disallowedTools "${NO_READ[@]}" < /dev/null > "$RUN/$step.json" 2>> "$RUN/err.log" \
    || { log_stop "the $step step failed"; echo "stopped: the $step step failed; see $RUN/err.log"; exit 1; }
  SPENT=$($LIB cost "$RUN/$step.json" "$SPENT" "$CAP") || { log_stop "over the \$$CAP cap at $step"; echo "stopped: over the \$$CAP cap at $step, $SPENT"; exit 1; }
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("result") or "")' "$RUN/$step.json" > "$RUN/$step.txt"
}

if [ "$CADENCE" = daily ]; then
  ask watch "$(route watch haiku)" "Step: watch. Cadence: daily. $SHARED" Read Grep Glob
  out=$RUN/watch.txt
else
  READ="Read Grep Glob WebFetch"
  ask research "$(route research sonnet)" "Step: research. $SHARED" $READ
  cp "$RUN/research.txt" "$CONTEXT/brief.md"
  STANDARDS="$KIT/standards/core.md $KIT/standards/checklists.md $KIT/standards/writing.md$(field Surfaces | tr ',|' '\n\n' | sed 's/[^a-z-]//g' | while read -r f; do [ -n "$f" ] && [ -f "$KIT/standards/$f.md" ] && printf ' %s' "$KIT/standards/$f.md"; done)"
  ask ux "$(route review sonnet)" "Step: audit. $SHARED Standards: $STANDARDS." Read Grep Glob
  { echo; cat "$RUN/ux.txt"; } >> "$CONTEXT/brief.md"
  ask ideas "$(route research sonnet)" "Step: new ideas. $SHARED" $READ
  cat "$RUN/ideas.txt" >> "$CONTEXT/brief.md"
  ask disprove "$(route disprove opus)" "Step: disprove. $SHARED Brief: $CONTEXT/brief.md." Read
  cp "$RUN/disprove.txt" "$CONTEXT/verdicts.md"
  ask decide "$(route decide opus)" "Step: decide. Cadence: weekly. $SHARED Brief: $CONTEXT/brief.md. Verdicts: $CONTEXT/verdicts.md. Last move: $($LIB last-move "$CONTEXT/decisions.md")." Read Grep Glob
  out=$RUN/decide.txt
fi
why=$(python3 "$KIT/scripts/file_memo.py" "$PROFILE" "$out") && done="weekly review filed" || done="weekly review not filed, $why"
# Its cost joins the team log, so the brief's totals count weekly and first reviews too.
LOGGED=1; echo "- $TODAY | $done | \$$SPENT" >> "$CONTEXT/team-log.md"
# The brief reaches the owner even when the record refuses the memo, and says so.
[ "$CADENCE" = daily ] || $LIB morning "$out" "$done" "$TODAY" "$KIT" "$CONTEXT" "$CAP_SET" > "$CONTEXT/morning.md"
[ "$CADENCE" = daily ] || CLAUDE=$CLAUDE bash "$KIT/scripts/brief_doc.sh" "$PROFILE" publish
# With a state repo, the first review goes there too, so teammates and cloud runs start from it.
STATE=$(field "State repo")
if [ -n "$STATE" ]; then
  if why2=$($LIB leaks "$CONTEXT"); then state_save "$CONTEXT" "$STATE" "$(basename "$(dirname "$(cd "$CONTEXT" && pwd)")") $TODAY: first review" || [ -z "${STATE_LEAK:-}" ] || { SAFE=1; echo "safety stop: the record holds $STATE_LEAK, so it was not saved; read $CONTEXT"; }
  else SAFE=1; echo "safety stop: the record holds $why2, so it was not saved; read $CONTEXT"; fi
fi
case $done in *"not filed"*) echo "$why; the message is at $out"; cat "$out"; [ -z "${STATE_MSG:-}" ] || printf '%s\n' "$STATE_MSG"; exit 1 ;; esac
cat "$out"
echo "cost: \$$SPENT"
# A record that did not reach the state repo is a failed run, whatever the agents did; the last line says what to do.
[ -z "${STATE_MSG:-}" ] || { echo "$STATE_MSG"; exit 4; }
