---
name: dualtrack-setup
description: Set up Dualtrack, the product operating system for Claude Code, on the current repo. Asks at most three plain questions (what to look at first, where Dualtrack's record lives, and the most a run may spend) and sets the rest to safe defaults it lists, then drafts the profile, checks first and spends nothing until the checks pass, runs a first review, takes the first call, and says how to run it every day. Use when the user says "set up dualtrack", "set up my product team", "install the team on this repo", or "add another repo to my team".
---

# Set up Dualtrack

Your job is to set Dualtrack up on the repo in the current folder, for someone who may never have used a terminal. Ask in full, plain sentences. Each time, say what the choice means for them before you ask. Do one step at a time, and say what each step did once it is done.

**Show each step as a card.** A bold title with the skill doing the work, then the question or result, then one grey line starting `↳` that says what it means for them. Number the steps as you go; never promise a total, because some steps are skipped. The skills:

- **⚙ Setup**: the checks, the questions and filing the profile.
- **◆ Planning**: the preview, the first review and the brief.
- **⛨ Safety check**: the box below, and anything that stops or holds a run.

For example:

> **⚙ Setup** · step 2
> Where should Dualtrack keep its record?
> ↳ Your code repo only ever gets code.

Words follow `<kit>/standards/writing.md`: the product speaks, each action comes with its consequence, and roles are skills, never characters.

**The kit folder** is `${CLAUDE_PLUGIN_ROOT}`, the installed plugin's folder. Commands below write `<kit>` for it. If that path still reads `${CLAUDE_PLUGIN_ROOT}` literally, the skill was copied in by hand, and the kit folder is two levels above this skill's own folder.

## 0. Check, before anything that costs money

Run the free checks first. A failing check costs nothing, and nothing is spent until they pass. They are code, so every setup checks the same things in the same order:

```sh
python3 <kit>/scripts/setup_check.py
```

Show its lines to the person as they are. If it exits 1, stop there: say the fix it printed, in one step, and that nothing was changed. Never fix their code, tests or repo yourself during setup, even if they ask; they make the fix, then run setup again. If a line says `ask` (an API key is set), ask whether they meant Dualtrack to bill that key, and stop if not. If `Tests need the network` says `ask`, ask: "Your tests need the internet. Should Dualtrack agents run them with the network on? They get no keys, can't read your home folder, and reach only the domains you allow. They called: <the test_domains fact>. Allow those?" Yes, or a list they edit: pass `--test-network on --allowed-domains "<the domains, comma-separated>"` to setup_apply. Allowed domains is written only from this answer; otherwise it is none, and the owner can add domains in profile.md later. No: stop, and say Dualtrack needs tests that pass offline. Keep the JSON on the last line: the questions below use its facts.

If they name a test command the check could not find, run it again with `--tests "<their command>"`.

If it prints `Already set up` (the facts say `"set_up": true`), Dualtrack was set up on this product from another
machine or person. Ask nothing and draft nothing: run `python3 <kit>/scripts/setup_apply.py --join`, show its
lines, and say this checkout now uses Dualtrack's record. Then go to section 5, with no preview. When `local_only` is true, skip
`--join`: Dualtrack state is already on this machine, so say this repo uses it and go to section 5.

When `local_state` is true, setup ran here before GitHub. Ask in plain text: "Put Dualtrack state on GitHub as a private
repo? Cloud runs and teammates need it." Yes: run setup_apply.py `--join --create-state`. No: change nothing. If it stops because Dualtrack state also holds other products, ask: "This also puts <the products it named> on GitHub, in the same private repo. Go ahead?" Yes: run it again with `--share-all`. Then go to section 5, with no preview.

When `local_only` is true, this repo has no GitHub remote yet. Say the check's `A GitHub repo` line as it is. Skip
question 2: Dualtrack state becomes a git repo beside this one, on this machine. Say plainly: "Without GitHub, Dualtrack gives you briefs only, no pull requests. Building a change needs a GitHub repo, and you can add one later."

When the checks pass, and before the first agent call, show this box as it is:

> **What Dualtrack can and cannot do**
> - It reads your repo and public pages. It does not change your code during setup.
> - By default, Dualtrack agents never push your main branch or merge. Each change goes to its own `team/` branch and arrives as a pull request for you to decide. If you turn Auto-merge on, a small change that passes every check merges on its own.
> - Code from a branch runs with a clean environment: no keys or tokens, and a throwaway home folder. By default it also runs in a sandbox with no outside network, and if there is no sandbox the run stops unless you accept the risk.
> - A run stops before it goes over its Run cap, the most one run may spend. You choose it below.

## 1. A preview, once the checks pass

First show `<kit>/docs/example.md` as written, without its heading. It is free and makes no model call.

Show what Dualtrack would work on. This is the first paid step, so it runs only after every check passed and they have seen the box above. If the check said `ask` about `ANTHROPIC_API_KEY`, the answer they gave stands. Say it takes under two minutes and under $0.20 of their Claude plan, then run:

```sh
python3 <kit>/scripts/preview.py
```

Show its lines as they are, except the JSON on the last line. If it lists bets, ask: "Start with one of these? Say its number, or none." A pick skips question 1: pass its title from the JSON to setup_apply as `--focus "<title>"`. Nothing from the preview is saved.

## 2. Ask the questions

Ask at most three questions, in this order. Everything else takes its recommended answer, and setup_apply lists those at the end with how to change each one. Skip a question only where it says so.

**Question 1.** Skip it when they picked a bet from the preview. Ask in plain text, because the answer is theirs in their own words: "What should Dualtrack look at first? For example: rank the open issues we are working on, or get more people to install it. Say none to let Dualtrack agents choose." Show the `work` fact from the check first, so they know what Dualtrack already sees. Their answer, unless it is none, goes to setup_apply as `--focus "<their words>"`.

**Question 2.** Skip it when `local_only` is true. Ask with the AskUserQuestion tool: "Where should Dualtrack keep its record: its notes, numbers, decisions and daily log?"
- "A private record repo (Recommended)": "Your code repo only ever gets code. One private repo holds the record for all your products, and Dualtrack can run in the cloud." When `state_repo_exists` is false, add: "It does not exist yet: setup creates <state_repo> as a private repo."
- "This computer only": "The record stays on this computer and out of git. Dualtrack can only run on this computer."

Only if `state_repo_holds` is not empty, say the check's `Dualtrack state` line as it is. Check the `visibility` fact. If it is PUBLIC, say before asking: "This repo is public, so Dualtrack's pull requests and their comments are public too. The record stays out of it either way, and Dualtrack holds a pull request that would show your numbers, an email address or a home path, and tells you why."

**Question 3.** Ask with the AskUserQuestion tool: "What's the most one run may spend?" Every brief shows what the run cost, and `costs.md` lists every call.
- "$10 a run (Recommended)": "A run stops before it goes over, and never starts a build it can't afford to review."
- "No limit": "Runs spend what they need. You still see every run's cost in the brief."
- "Another amount": "Type a dollar amount for each run."
Pass the answer as `--run-cap <dollars>`, or `--run-cap none`.

Pass nothing else from the person. Pass `--design yes` when `web` is true. Their git name is the bets' owner; when `git_name` is empty, leave it out.

## 3. Set it up

Say that the next step reads the repo and its public pages, and takes a few minutes. Run, from the repo's root:

```sh
. <kit>/scripts/guards.sh && claude -p "Repo: . Today is $(date +%F). The moves are in <kit>/moves.md." --append-system-prompt-file <kit>/agents/setup.md --permission-mode dontAsk --max-budget-usd "${SETUP_BUDGET:-2}" --output-format json --allowedTools Read Grep Glob WebFetch --disallowedTools "${NO_READ[@]}" < /dev/null > setup.json && python3 -c 'import json; open("setup.md", "w").write(json.load(open("setup.json")).get("result") or "")' 
```

The call loads the kit's read-deny list first (keys, logins and env files stay unreadable). The setup call stops at $2. To give it more, put `SETUP_BUDGET=<dollars>` in front of the command.

Then file it with their answers. This is code too, so every setup files the same way:

```sh
python3 <kit>/scripts/setup_apply.py [--record local] [--design yes] [--tests "<the tests fact>"] [--test-network on --allowed-domains "<domains>"] [--focus "<question 1, in their words>"] --run-cap <question 3>
```

Add `--create-state` only when they chose the record repo and `state_repo_exists` was false. Show its lines as they are, and report only what they say: if a line says NOT pushed, say so. Its last line is the profile path. If it stops, show the reason and stop.

Then set up their numbers, so the first brief uses real data. First show this card as it is:

> **⛨ Safety check** · what happens to your numbers
> - Your notes and numbers stay in your repos, or on this computer if you chose that.
> - Tools connect read-only. Dualtrack cannot change anything in them.
> - No Dualtrack server: nothing is sent to Dualtrack's maker.
> - Claude reads what each step needs, through your own Claude plan.
> ↳ You can disconnect a tool at any time.

Then ask with the AskUserQuestion tool: "How should Dualtrack see your numbers?"
- "Connect a tool, read-only (Recommended)": "Dualtrack reads analytics, experiments or your tracker each run."
- "Paste them into numbers.md": "Type counts by hand in `numbers.md`, next to the profile. Write unknown where you have none."
- "Skip for now": "The first brief works from your repo and public pages."

Paste: say where `numbers.md` is, from setup_apply's `filed:` line, and go on to section 4. Skip: go on to section 4. Connect: run `python3 <kit>/scripts/sources.py menu`, show its lines as they are, and ask which to connect, by name. For each name, say its `ask` from `<kit>/sources.json`: that is exactly what Dualtrack reads. Say that what it finds stays in their repos. Then follow sections 2 and 3 of `<kit>/skills/dualtrack-connect/SKILL.md`. One that fails to connect is skipped, not retried.

## 4. First review, and the first call

Setup ends with a live first run; do not ask whether to run it. Say that it starts now, takes a few minutes and uses their Claude plan, about $1.11 to $2.85 in the runs measured so far, then run `bash <kit>/scripts/run.sh <profile path>`. If it stops, show the reason and the one step that fixes it, then run it again once that step is done.

When it finishes, show the brief with `/dualtrack:dualtrack-team`: its top bet, with the reason, and the Decisions table. Ask for one call in plain words: "build 1", "none of these, because ...", or "do X instead". Run it with `decide.py`, as `<kit>/skills/dualtrack/SKILL.md` section 3 describes, and show what it printed. Building a change needs GitHub, so when `local_only` is true say instead: "Without GitHub you get briefs only, no pull requests. Your pick is kept. To build it, add a GitHub repo with `gh repo create`, then run again." They can also say they will decide later: then go on.

## 5. Every day

Only now, after the first call, give them the exact steps from `<kit>/docs/schedule.md` for the way they chose, with every placeholder filled in: their repo, their state repo, and the profile path. You cannot set up the schedule yourself. They paste one request into `/schedule`, or one `/loop` line. Say so.

## 6. Then

- Ask them to answer the questions in `setup-notes.md` when they can. Each answer sharpens the next run.
- To add another repo, they run this skill again in that repo, and choose the same state repo.
- Dualtrack agents open ready pull requests, and they decide. Only with Auto-merge on does a small change that passes every check merge without them; the team log (team-log.md) then says how to undo it.
- To ask for changes, they comment on the pull request, in general or on a line. The next run builds the comments on that same pull request. GitHub does not let anyone press Request changes on their own pull request, so in personal mode a comment is the way. Anyone with write access to the repo can ask, so they should check who has it.
- To ask Dualtrack's maker for a feature, they run /dualtrack:dualtrack-request.

Never edit their code, merge, or push anything except the state repo during setup.
