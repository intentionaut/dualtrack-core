#!/bin/bash
# one.sh <arm a|b> <n>: one engineer run on a fresh clone of $FIX.
# arm-a.md = agents/engineer.md. arm-b.md = agents/engineer.md, then ponytail's skills/ponytail/SKILL.md (v5.3.2).
set -u
B=$(cd "$(dirname "$0")" && pwd); arm=$1; n=$2
W=$B/runs/$arm-$n; rm -rf "$W"; git clone -q "$FIX" "$W/repo" && cd "$W/repo" && git checkout -q -b exp
BASE=$(git rev-parse HEAD)
ITEM='{"title": "Add table(rows) to textkit", "done_when": ["table(rows) takes a list of dicts and returns a Markdown table string: a header row, a --- separator row, one row per dict", "columns are the keys in first-seen order across all rows; a missing value is an empty cell", "a | inside a value is escaped as \\|", "table([]) returns an empty string", "tests cover each line above"], "size": "small", "visible": false}'
start=$(date +%s)
claude -p "Build this item on the current branch, exp. Do not change branch. Item: $ITEM. Profile: none. Test command: python3 -m unittest discover -s tests." \
  --append-system-prompt-file "$B/arm-$arm.md" --model sonnet --setting-sources project,local \
  --permission-mode dontAsk --output-format json --allowedTools Read Glob Grep Edit Write Bash \
  --disallowedTools "Bash(git push:*)" "Bash(gh:*)" < /dev/null > "$W/out.json" 2> "$W/err.log"
end=$(date +%s)
git add -A >/dev/null 2>&1; git -c user.name=b -c user.email=b@b.invalid commit -qm leftover >/dev/null 2>&1
python3 - "$W" "$arm" "$n" "$BASE" "$((end-start))" "$B" <<'PY'
import json, subprocess, sys
w, arm, n, base, secs, b = sys.argv[1:7]
repo = f"{w}/repo"
num = subprocess.run(["git", "-C", repo, "diff", "--numstat", base, "HEAD"], capture_output=True, text=True).stdout.split("\n")
code = tests = 0; files = []
for l in num:
    if not l.strip(): continue
    a, d, f = l.split("\t"); files.append(f)
    if f.endswith(".py") and ("test" in f): tests += int(a)
    elif f.endswith(".py"): code += int(a)
acc = subprocess.run([sys.executable, f"{b}/accept.py", repo], capture_output=True, text=True)
own = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=repo, capture_output=True, text=True)
try: out = json.load(open(f"{w}/out.json"))
except Exception: out = {}
deps = any(f in ("requirements.txt", "pyproject.toml", "setup.py") for f in files)
print(json.dumps({"arm": arm, "n": int(n), "code_lines": code, "test_lines": tests, "files": files, "accept_pass": acc.returncode == 0,
  "own_tests_pass": own.returncode == 0, "cost": out.get("total_cost_usd"), "turns": out.get("num_turns"), "secs": int(secs),
  "first_line": (out.get("result") or "").strip().split("\n")[0][:60], "new_dep": deps}))
PY
