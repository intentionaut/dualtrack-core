#!/bin/bash
# Put the morning brief in a Claude doc, and read the owner's calls back from it.
#
# Usage: bash scripts/brief_doc.sh <profile.md> publish|collect
# Runs only if the profile says **Brief doc:** claude, or names a doc link. Never stops the loop.
set -uo pipefail
KIT=$(cd "$(dirname "$0")/.." && pwd)
PROFILE=$1; STEP=$2; CLAUDE=${CLAUDE:-claude}
field() { sed -n "s/^\*\*$1:\*\* *//p" "$PROFILE" | head -1; }
WANT=$(field "Brief doc"); CONTEXT=$(field "Context path"); NAME=$(field "Product"); NAME=${NAME:-this product}
case $WANT in claude*|http*) ;; *) exit 0 ;; esac
STATE="$CONTEXT/brief-doc.txt"
DOC=$(cat "$STATE" 2>/dev/null || true); [ -n "$DOC" ] || case $WANT in http*) DOC=$WANT ;; esac
. "$KIT/scripts/guards.sh"
# Not LEAN: the claude.ai Docs connector comes with user settings, so those stay. Project and local settings are
# dropped, so a hook or CLAUDE.md in the repo cannot ride along.
# No budget of its own: the loop passes what is left of the owner's Run cap, and a run by hand has none.
GUARD=(--disable-slash-commands --setting-sources user ${BRIEF_BUDGET:+--max-budget-usd "$BRIEF_BUDGET"} --disallowedTools "${NO_READ[@]}")
TOOLS="mcp__claude_ai_Claude_Docs__guide mcp__claude_ai_Claude_Docs__read mcp__claude_ai_Claude_Docs__query ToolSearch"
# Each call's JSON is kept, so its cost lands in costs.md like every other agent call's, and the loop can add it to
# the run's total (BRIEF_COST_FILE). The text answer is the JSON's result.
J=$(mktemp); trap 'rm -f "$J"' EXIT
priced() { local step=$1 c; c=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("total_cost_usd", ""))' "$J" 2>/dev/null)
  echo "- $DATE | brief doc $step | ${BRIEF_MODEL:-sonnet} | \$${c:-unknown}" >> "$CONTEXT/costs.md"
  [ -z "${BRIEF_COST_FILE:-}" ] || cp "$J" "$BRIEF_COST_FILE"
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("result") or "")' "$J" 2>/dev/null; }
DATE=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["date"])' "$CONTEXT/options.json" 2>/dev/null || date +%F)

if [ "$STEP" = publish ]; then
  # Each publish is a paid session: skip it for a preflight and when the brief has not changed since the last one.
  [ -z "${PREFLIGHT:-}" ] || exit 0
  sum=$(cksum < "$CONTEXT/morning.md" 2>/dev/null)
  [ -n "$DOC" ] && [ "$sum" = "$(cat "$CONTEXT/brief-doc.sum" 2>/dev/null)" ] && { echo "brief doc: $DOC (unchanged)"; exit 0; }
  out=$("$CLAUDE" -p "Brief file: $CONTEXT/morning.md. Product: $NAME. Date: $DATE. Doc: ${DOC:-none}." \
    --append-system-prompt-file "$KIT/prompts/brief-doc-publish.md" --model "${BRIEF_MODEL:-sonnet}" "${GUARD[@]}" \
    --permission-mode dontAsk --output-format json --allowedTools Read $TOOLS mcp__claude_ai_Claude_Docs__batch mcp__claude_ai_Claude_Docs__update \
    < /dev/null > "$J" 2>/dev/null; priced publish | tail -1)
  case $out in
    "DOC: http"*) echo "${out#DOC: }" > "$STATE"; echo "$sum" > "$CONTEXT/brief-doc.sum"; echo "brief doc: ${out#DOC: }" ;;
    *) echo "brief doc not updated: ${out:-no answer}; the brief is in $CONTEXT/morning.md" ;;
  esac
  exit 0
fi

# collect: once per brief, the owner's calls become decide.py answers.
[ -n "$DOC" ] || exit 0
grep -qx "$DATE" "$CONTEXT/brief-doc-read.txt" 2>/dev/null && exit 0
"$CLAUDE" -p "Doc: $DOC. Date: $DATE." --append-system-prompt-file "$KIT/prompts/brief-doc-collect.md" \
  --model "${BRIEF_MODEL:-sonnet}" "${GUARD[@]}" --permission-mode dontAsk --output-format json --allowedTools $TOOLS < /dev/null > "$J" 2>/dev/null
priced collect | python3 "$KIT/scripts/decide.py" --from-doc && echo "$DATE" >> "$CONTEXT/brief-doc-read.txt"
exit 0
