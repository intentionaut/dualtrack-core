---
allowed-tools: Read, Glob, Grep, Agent, Task, Bash(<ghrest> pr info:*), Bash(<ghrest> pr diff:*), Bash(<ghrest> pr files:*)
description: Code review a pull request, read-only, over REST
---

<!--
ADAPTATION. Source: commands/code-review.md of Anthropic's code-review plugin 1.0.1, from the
claude-plugins-official marketplace, snapshot fa4eb54397ee2faccb6940512a19c017cb1337f3
(source file sha256 3f02ea6eed996590348264777b2e324859a6e2c0c5f7dd298617ea21deb3b1b2).
Licensed under the Apache License 2.0: see LICENSE and NOTICE in this folder.
What changed: every gh call (gh pr view, gh pr diff, gh pr list, gh issue, gh search use GraphQL
or are not needed) is replaced by read-only REST subcommands of scripts/ghrest.py; the `--comment`
option, steps 8 and 9 and every way to post a comment were removed, so the review only prints to
the terminal; the allowed tools are read-only. The review never reads the pull request's comments
or reviews, so anyone who can comment cannot plant a verdict or orders, and the "already commented"
check is dropped with them. The other review steps and eligibility checks are kept.
`<ghrest>` is replaced by the loop with the path to ghrest.py.
-->

Provide a code review for the given pull request. This review only reads. Never post, comment, review, edit or merge anything.

GitHub reads, all read-only, where `<n>` is the pull request number:
- `<ghrest> pr info <n>`: title, body, state, draft, author, head commit and base branch, as JSON
- `<ghrest> pr diff <n>`: the diff
- `<ghrest> pr files <n>`: the changed file paths

**Agent assumptions (applies to all agents and subagents):**
- All tools are functional and will work without error. Do not test tools or make exploratory calls. Make sure this is clear to every subagent that is launched.
- Only call a tool if it is required to complete the task. Every tool call should have a clear purpose.
- Use only the GitHub reads listed above. Tell every subagent the same.

To do this, follow these steps precisely:

1. Launch a haiku agent to check if any of the following are true:
   - The pull request is closed
   - The pull request is a draft
   - The pull request does not need code review (e.g. automated PR, trivial change that is obviously correct)

   If any condition is true, print `Skipped: <which condition>` and stop.

Note: Still review Claude generated PR's.

2. Launch a haiku agent to return a list of file paths (not their contents) for all relevant CLAUDE.md files including:
   - The root CLAUDE.md file, if it exists
   - Any CLAUDE.md files in directories containing files modified by the pull request (`<ghrest> pr files <n>`)

3. Launch a sonnet agent to view the pull request (`<ghrest> pr info <n>` and `<ghrest> pr diff <n>`) and return a summary of the changes

4. Launch 4 agents in parallel to independently review the changes. Each agent should return the list of issues, where each issue includes a description and the reason it was flagged (e.g. "CLAUDE.md adherence", "bug"). The agents should do the following:

   Agents 1 + 2: CLAUDE.md compliance sonnet agents
   Audit changes for CLAUDE.md compliance in parallel. Note: When evaluating CLAUDE.md compliance for a file, you should only consider CLAUDE.md files that share a file path with the file or parents.

   Agent 3: Opus bug agent (parallel subagent with agent 4)
   Scan for obvious bugs. Focus only on the diff itself without reading extra context. Flag only significant bugs; ignore nitpicks and likely false positives. Do not flag issues that you cannot validate without looking at context outside of the git diff.

   Agent 4: Opus bug agent (parallel subagent with agent 3)
   Look for problems that exist in the introduced code. This could be security issues, incorrect logic, etc. Only look for issues that fall within the changed code.

   **CRITICAL: We only want HIGH SIGNAL issues.** Flag issues where:
   - The code will fail to compile or parse (syntax errors, type errors, missing imports, unresolved references)
   - The code will definitely produce wrong results regardless of inputs (clear logic errors)
   - Clear, unambiguous CLAUDE.md violations where you can quote the exact rule being broken

   Do NOT flag:
   - Code style or quality concerns
   - Potential issues that depend on specific inputs or state
   - Subjective suggestions or improvements

   If you are not certain an issue is real, do not flag it. False positives erode trust and waste reviewer time.

   In addition to the above, each subagent should be told the PR title and description. This will help provide context regarding the author's intent.

5. For each issue found in the previous step by agents 3 and 4, launch parallel subagents to validate the issue. These subagents should get the PR title and description along with a description of the issue. The agent's job is to review the issue to validate that the stated issue is truly an issue with high confidence. For example, if an issue such as "variable is not defined" was flagged, the subagent's job would be to validate that is actually true in the code. Another example would be CLAUDE.md issues. The agent should validate that the CLAUDE.md rule that was violated is scoped for this file and is actually violated. Use Opus subagents for bugs and logic issues, and sonnet agents for CLAUDE.md violations.

6. Filter out any issues that were not validated in step 5. This step will give us our list of high signal issues for our review.

7. Output a summary of the review findings to the terminal, and stop. Post nothing anywhere.
   - If issues were found, list each issue with a brief description, the file and lines.
   - If no issues were found, state exactly: "No issues found. Checked for bugs and CLAUDE.md compliance."

Use this list when evaluating issues in Steps 4 and 5 (these are false positives, do NOT flag):

- Pre-existing issues
- Something that appears to be a bug but is actually correct
- Pedantic nitpicks that a senior engineer would not flag
- Issues that a linter will catch (do not run the linter to verify)
- General code quality concerns (e.g., lack of test coverage, general security issues) unless explicitly required in CLAUDE.md
- Issues mentioned in CLAUDE.md but explicitly silenced in the code (e.g., via a lint ignore comment)

Notes:

- Use only the GitHub reads listed above. Do not use gh directly, and do not use web fetch.
- Create a todo list before starting.
- Cite each issue with its file and line range.
