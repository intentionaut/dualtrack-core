# Sourced by every script that starts an agent, so they all refuse the same things.
# LEAN: no user or project settings, plugins, hooks or slash commands, so a write into the repo can't add a hook or
# permission to the next agent, and the owner's own setup never rides along.
LEAN="--disable-slash-commands --setting-sources="
# What no agent may read: the home folder's keys and logins, the App's key, and env files.
NO_READ=("Read(**/outside-new.md)" "Read(**/last-run/**)" "Read(~/.ssh/**)" "Read(~/.aws/**)" "Read(~/.gnupg/**)" "Read(~/.config/**)" "Read(~/.netrc)" "Read(~/.npmrc)"
  "Read(~/.docker/**)" "Read(~/.kube/**)" "Read(~/.claude/.credentials.json)" "Read(~/.claude.json)" "Read(**/.env)" "Read(**/.env.*)")
[ -z "${DUALTRACK_APP_KEY:-}" ] || NO_READ+=("Read(/${DUALTRACK_APP_KEY#/})")
# state_save <context> <state repo> <message> [lock file]: commit only this product's folder and push it, so runs for
# other products can share one state checkout. A refused push is rebased once. If that fails too, the rebase is
# aborted (the commit stays, the checkout stays on its branch), the run lock is taken off origin alone, and STATE_MSG
# names the one step that finishes the save; the caller prints it and exits non-zero. A secret in what was staged
# unstages it, frees the lock and returns 2 with STATE_LEAK naming it: held, not failed.
# A state repo must be a git repo of its own: a folder inside the product repo would push the record there.
state_save() { local mine; [ "$(git -C "$2" rev-parse --show-toplevel 2>/dev/null)" = "$(cd "$2" 2>/dev/null && pwd -P)" ] \
  || { STATE_MSG="state not saved: $2 is not a git repo of its own, so the record stays only in $1"; echo "$STATE_MSG"; return 1; }
  mine=$(cd "$1" && pwd) && git -C "$2" add -A -- "$mine" \
  && { staged_leak "$2" "$mine" || { STATE_LEAK=$why; git -C "$2" reset -q -- "$mine"; [ -z "${4:-}" ] || state_unlock "$2" "$4"; return 2; }; } \
  && { git -C "$2" diff --cached --quiet -- "$mine" || git -C "$2" commit -qm "$3" -- "$mine"; } \
  && { [ -z "$(git -C "$2" remote)" ] || "${NET_GIT[@]}" -C "$2" push -q || { "${NET_GIT[@]}" -C "$2" pull -q --rebase --autostash && "${NET_GIT[@]}" -C "$2" push -q; }; } && return 0
  git -C "$2" rebase --abort 2>/dev/null; [ -z "${4:-}" ] || state_unlock "$2" "$4"
  STATE_MSG="state not saved: the record is committed in $2 but not pushed; run: git -C $2 pull --rebase && git -C $2 push (on a conflict, fix the files it names first)"; return 1; }
# staged_leak <state repo> <folder>: scan the lines about to be committed, not the files as they were earlier. Sets $why.
staged_leak() { local f; f=$(mktemp); git -C "$1" diff --cached -U0 --no-color -- "$2" | grep -a '^+' | grep -av '^+++ ' > "$f"
  why=$(python3 "$(dirname "${BASH_SOURCE[0]}")/loop_lib.py" leaks "$f"); local rc=$?; rm -f "$f"; [ $rc = 0 ]; }
# state_unlock <state repo> <lock file>: take a run lock off origin in a commit that touches nothing else, so it
# never conflicts with the record.
state_unlock() { local up rel idx c; up=$(git -C "$1" rev-parse --abbrev-ref '@{u}' 2>/dev/null) && "${NET_GIT[@]}" -C "$1" fetch -q 2>/dev/null || return 0
  rel=$(git -C "$(dirname "$2")" rev-parse --show-prefix)$(basename "$2"); git -C "$1" cat-file -e "$up:$rel" 2>/dev/null || return 0
  idx=$(mktemp -u); GIT_INDEX_FILE=$idx git -C "$1" read-tree "$up" && GIT_INDEX_FILE=$idx git -C "$1" update-index --force-remove -- "$rel" \
    && c=$(git -C "$1" commit-tree "$(GIT_INDEX_FILE=$idx git -C "$1" write-tree)" -p "$up" -m "run lock released") \
    && "${NET_GIT[@]}" -C "$1" push -q "${up%/*}" "$c:refs/heads/${up#*/}" 2>/dev/null; rm -f "$idx"; return 0; }
# Every agent call is cut off after AGENT_TIMEOUT seconds (default 30 minutes), with everything it started; macOS has no timeout.
# Network git (the state repo's push and pull) is cut off after NET_TIMEOUT seconds (default 2 minutes) and never waits on a password prompt.
NET_GIT=(python3 "$(dirname "${BASH_SOURCE[0]}")/limit.py" "${NET_TIMEOUT:-120}" env GIT_TERMINAL_PROMPT=0 git)
AGENT_LIMIT=(python3 "$(dirname "${BASH_SOURCE[0]}")/limit.py" "${AGENT_TIMEOUT:-1800}")
