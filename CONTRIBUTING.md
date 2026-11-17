# Contributing

Dualtrack is a kit of scripts and agent prompts. A change is a pull request against `main`. This page says how to make one that can be reviewed quickly.

## Run the tests

Python 3.9 or later and Bash are needed. From the repo root:

```sh
python3 -m unittest discover tests
```

The suite must pass before a pull request is opened. CI runs the same suite on every pull request.

## What belongs in this repo

This repo is the free kit. Features the [pricing page](https://dualtrack.intentionaut.com/pricing/) lists under Team, Business or Enterprise are not built here. If an issue or a task asks for one, say so on the issue and stop. This applies to people and to AI agents.

## Make a change

1. One change per pull request. A fix and a tidy-up are two pull requests.
2. Write a test that fails first. Run it on the unchanged code and see it fail, make the change, then see it pass. Put the failing and passing lines in the pull request.
3. Keep the code's existing style: short lines, and a one-line comment that says why, not what.
4. Use a Conventional Commits subject, for example `fix(loop): ...` or `docs(readme): ...`.
5. Do not merge your own pull request. A maintainer merges it.

## Writing rules

- British English: "behaviour", "optimise", "organisation".
- Plain words. Define a term the first time it appears. Put exact commands in code blocks.
- Every skill name contains "dualtrack"; the front door is exactly "dualtrack". `tests/test_skill_names.py` checks it.
- No personal names, home paths or private product names in any file. `tests/test_kit.py` fails the suite if it finds one.

## Reporting problems

- A bug or an idea: open an issue and pick the matching form.
- A security problem: do not open an issue. Follow `SECURITY.md`.

By taking part, everyone agrees to `CODE_OF_CONDUCT.md`.
