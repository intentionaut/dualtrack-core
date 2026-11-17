# Engineer with and without ponytail

Run on 2026-11-04. One task, 10 runs per arm, 10 at a time.

| | Without ponytail | With ponytail |
|---|---:|---:|
| Code lines added, median (range) | 20 (16 to 21) | **11 (9 to 13)** |
| Test lines added, median (range) | 21.5 (18 to 24) | 19 (19 to 21) |
| Hidden acceptance test passed | 10 of 10 | 10 of 10 |
| Its own tests passed | 10 of 10 | 10 of 10 |
| New dependencies | 0 | 0 |
| Cost per run, median | $0.144 | $0.148 |
| Turns, median | 6 | 6 |
| Time, median | 20.5 s | 19 s |

With ponytail, the engineer wrote about half the code. The ranges do not overlap. It was just as correct, and cost and time did not change: the $0.004 gap in median cost is inside the run-to-run spread (standard deviation $0.026 in both arms). Costs in both arms fall in two groups, about $0.12 and $0.17, most likely prompt-cache hits and misses across parallel runs.

## Method

- **Task:** add `table(rows)` to `fixture/textkit.py`. The function turns a list of dicts into a Markdown table, with columns in first-seen order, blank cells for missing values, `|` escaped, and `""` for an empty list. The item and its "Done when" lines are in `one.sh`.
- **Arms:** A gives the engineer `agents/engineer.md` only. B gives it `agents/engineer.md` followed by ponytail's `skills/ponytail/SKILL.md`, v5.3.2, MIT.
- **Same in both arms:** Claude Code headless (`claude -p`) and the `sonnet` model. The engineer's tools are Read, Glob, Grep, Edit, Write and Bash, with `--setting-sources project,local`, so the user's plugins and hooks load in neither arm. Each run starts from a fresh clone.
- **Measured:** lines added from `git diff --numstat`, split into test files and code files. Code lines include docstrings and blank lines. `accept.py` is a hidden acceptance test that the agent never sees. The test also checks that the agent's own tests pass, and reads cost and turns from Claude Code's JSON output.
- **Raw data:** `results.jsonl`, one line per run.

## Limits

- This is one small task in one language, so it does not show results for large changes or other stacks.
- 10 runs per arm is enough to see a gap this wide, not a small one.
- Arm B measures ponytail's rules, not the ponytail plugin. In Dualtrack's headless runs, the plugin's hooks and band do not load, so the rules have to be in the prompt.

## Reproduce

```sh
git init fixture-repo && cp -R fixture/. fixture-repo/ && git -C fixture-repo add -A && git -C fixture-repo commit -qm fixture
cp ../../agents/engineer.md arm-a.md
{ cat ../../agents/engineer.md; echo; echo ---; echo; cat <ponytail>/skills/ponytail/SKILL.md; } > arm-b.md
export FIX=$PWD/fixture-repo
for i in $(seq 1 10); do echo "a $i"; echo "b $i"; done | xargs -P 10 -L 1 bash one.sh > results.jsonl
```
