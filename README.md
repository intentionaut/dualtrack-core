# Dualtrack

By [Saielle DaSilva](https://intentionaut.com), Fractional Product Leader. <!-- credit -->

The product operating system for Claude Code. It proposes product bets, builds changes in your repo, and records what each one did. For anything your users would see, each run brings you a table of decisions:

| # | Change | Reason | Expected outcome |
|---|---|---|---|
| 1 | Add a demo page | 3 of 40 visitors ask how it works | more first runs by 1 December |
| 2 | Fix the install step | 2 reports of a failed build | fewer failed installs |

You answer in one line. Dualtrack builds your pick, a second review reads the change, and a ready pull request waits for you. Auto-merge is off by default. Turn it on and changes of up to 50 lines in up to 3 files that pass every check merge on their own (see Limits).

Dualtrack is self-hosted and sends nothing to its maker: agents call the model provider you configure, and the records live in your own repos. What goes where, and how to turn each part off: `docs/data.md`.

It follows the **Dual Track Agent Team** method:

| Track | Runs | Covers |
|---|---|---|
| Automatic | on its own | research; changes of any size that no person would see (tests, broken links, metadata), when nothing on the stop list is touched |
| Owner | merges only with you, unless you turn on Auto-merge | anything a person would see: designed, built and reviewed; it may be built before your pick, and the pull request says so |

Licence: FSL-1.1-ALv2. Source-available, free to use, and each release becomes Apache 2.0 after two years (see Licence).

## Quick start

In Claude Code, install the plugin:

```
/plugin marketplace add intentionaut/dualtrack-core
/plugin install dualtrack@dualtrack
```

Then, in any product repo, type `/dualtrack:dualtrack`.

Before you start you need Claude Code logged in, Python 3.9 or later, and Bash. For pull requests you also need a GitHub repo, `gh` logged in, and tests that run locally. On Ubuntu 24.04, setup needs one machine-wide `sudo` change first: see Requirements. To see what a run produces before you try one, read the sample memos in `example/memos/`.

## Requirements

- Claude Code, logged in. A Claude subscription covers it if `ANTHROPIC_API_KEY` is unset.
- Python 3.9 or later, and Bash.
- Dualtrack Free covers up to 6 product teams in one state repo. Setup stops before a 7th; 7 or more is the Team tier, which is not open yet. The 6 already set up keep running.
- For the daily loop: a GitHub repo, `gh` logged in, and tests that run locally. Three kinds of test work:
  - **Offline tests** run on every change. This is the default.
  - **Tests that call the internet** (to download a package index, for example) also run on every change, with **Test network** on. Setup sees that they need the internet, shows you the domains they call, and allows only those after you say yes. They have to use HTTP or HTTPS through the standard proxy setting. Python, curl and Go do this; Node does from version 22.
  - **Tests that need real keys** for a live service, such as a payments or AI API, run in CI only, never on your machine. Name that CI check under **Required checks**, and Dualtrack agents wait for it.
- For Auto-merge: CI on GitHub as well. Setup doesn't check for it, and nothing merges on its own without it.
- Tested on macOS (Seatbelt sandbox) and Linux (bubblewrap, on Ubuntu in CI). Windows untested; on Windows use WSL or Git Bash.
- On Ubuntu 24.04, bubblewrap also needs the kernel to let it create user namespaces. Run `echo 'kernel.apparmor_restrict_unprivileged_userns=0' | sudo tee /etc/sysctl.d/60-dualtrack-bwrap.conf && sudo sysctl --system`. That setting applies to the whole machine, not only Dualtrack, and the one-off form (sudo sysctl -w) is lost on reboot. Without it the run stops and says so, and setup checks for it early.

## Set up

In Claude Code, install the plugin once:

```
/plugin marketplace add intentionaut/dualtrack-core
/plugin install dualtrack@dualtrack
```

From a local clone instead, use its folder: `/plugin marketplace add ./path/to/dualtrack-core`.

Once installed, type `/dualtrack:dualtrack` to start.

Run it in any product repo. The first run checks the repo for free, asks at most three plain questions with a recommended answer each, writes the profile and runs the first review. Your code doesn't change. If you keep the record in a private repo, setup asks first, then creates that repo in your GitHub account and pushes Dualtrack's notes there. No GitHub repo yet? Setup still works and keeps the record on this computer, but without GitHub Dualtrack gives you briefs only, no pull requests. Add a GitHub repo later and it builds your picks. No numbers are needed to start: Dualtrack agents work from public evidence and list what they do not know.

After that, `/dualtrack:dualtrack` is the only command you need. Each time, it does the next thing: shows the brief and takes your call in plain words ("build 2", "none of these, because..."), points you to a pull request to review, asks Dualtrack's question, or runs Dualtrack agents.

To open your dashboard, say `/dualtrack dashboard`, "show my dashboard" or "open the dashboard".

To ask Dualtrack's maker for a feature, type `/dualtrack:dualtrack-request`. It drafts the request with you and opens a filled-in GitHub issue or email; nothing is sent until you submit it.

**In a squad:** keep the record in a state repo everyone can push to. A teammate runs `/dualtrack:dualtrack` in their own clone, and setup joins the existing record instead of asking again. Its history names who made each call. One run goes at a time across all your machines: a run takes a lock in the state repo, and a second machine's run stops until it is done. Anyone with write access to the product repo can ask for changes on Dualtrack's pull requests.

<details>
<summary>Without the plugin</summary>

Clone the kit beside your repo, so it sits at `../dualtrack-core`:

```sh
git clone https://github.com/intentionaut/dualtrack-core.git ../dualtrack-core
```

Then, from your repo's root:

```sh
mkdir -p .claude/agents .claude/skills && cp ../dualtrack-core/agents/*.md .claude/agents/ && cp -R ../dualtrack-core/skills/dualtrack-team .claude/skills/
claude -p "Repo: . Today is $(date +%F). The moves are in ../dualtrack-core/moves.md." --agent setup --permission-mode dontAsk --allowedTools Read Grep Glob WebFetch < /dev/null > setup.md
python3 ../dualtrack-core/scripts/file_setup.py setup.md
bash ../dualtrack-core/scripts/run.sh profile.md
```

| Step | Writes |
|---|---|
| `setup` agent | `setup.md`: a draft profile from your repo and public pages |
| `file_setup.py` | `profile.md`, `setup-notes.md`, `product-context/`, empty `numbers.md` |
| `run.sh` | first weekly review, first brief, and the brief's link |

</details>

## Safety checks

Each run's checks are listed on its pull request under **Safety checks**, in the morning brief when one held or could not run, and in the event. A check that could not run says so; it never reads as passed.

- Code from a branch (tests, installs, design checks) runs with a clean environment: no keys, no agent socket and a throwaway home folder. The one token in it is a fake canary (see **Watching for leaks**); setup's install commands also get a Setup token, only if the loop holds one. On macOS it also runs in a sandbox with no writes outside the checkout and temporary folders and no reads from secret folders and files such as `~/.ssh`, `~/.config`, `~/.git-credentials` and `~/.pypirc`; on Linux it uses bubblewrap, which hides the same list. Installs (**Setup commands**) run with the network open and the home folder closed. Tests and design checks have no outside network unless **Test network** is on, below. While a run is going, another Dualtrack run's temporary folder on the same Mac can be read by its tests. With **Test network** on, the macOS sandbox closes the whole home folder. With neither tool, the run stops and the brief says to install bubblewrap, unless the profile says `**Sandbox:** none, I accept the risk`, in which case the check says the sandbox was unavailable and the code runs with the same clean environment but an open network and no limit on the files it can read. Company mode never accepts that.
- Setup's own test run uses the same clean environment, with a lighter box: no outside network, including DNS, on macOS and Linux (except through its recording proxy while it learns the domains for **Test network**), and your home folder is not hidden, except with **Test network** on. With **Test network** on, Linux uses bubblewrap for that run: your home folder is closed, but code that skips the proxy can still reach the network.
- With **Test network** on, the tests reach only the profile's **Allowed domains**, through a local proxy. The sandbox lets them reach nothing but your own machine, so code that skips the proxy (a raw socket, or a client that ignores `HTTPS_PROXY`) fails rather than getting out. The whole home folder and the run's own files are closed to them too, except the checkout and language toolchains (their login files stay closed), and they get no keys. Setup runs the tests once to learn which domains they call, and asks you before allowing them. When a test tries a domain you haven't allowed, the brief names it, so you can add it. An allowed domain may hold one `*` in its first label for preview hosts, such as `myapp-*.vercel.app`; on shared hosts like `vercel.app` it needs a fixed prefix before the `*`.
- Agents' shells run in Claude Code's sandbox. The engineer's shell can stage and commit on its branch (`git add`, `commit`, `status`, `rm`, `mv`). `git push`, `gh` and writes to `.git/**` are denied. Agents cannot read the home folder's keys, logins or `.env` files.
- After every agent, git's own settings in `.git` are compared with how the loop left them. A change is undone and the run stops.
- The whole change is scanned for secrets before it is pushed, and the record before it is saved.
- A source's output that holds a secret, an email address or a home path is dropped, never masked, and the brief says which source.
- PR comments are data: only the repo's team gives a close reason, and every comment is flattened to one line.

## With other agents and workflows

Every run leaves a `dualtrack.run.v1` event in `product-context/events/` and, if you set `DUALTRACK_WEBHOOK_URL`, posts it there signed. Zapier, n8n, Make, Workato or Power Automate can route it to Slack, Teams, email or a ticket. Other agents read the product's context with `python3 ../dualtrack-core/scripts/handoff.py context profile.md` and steer Dualtrack agents through `decide.py`. See `docs/handoff.md`.

## Company mode

For a team inside a company. Set `**Company mode:** on` in the profile. Then:

| What | How it is enforced |
|---|---|
| Runs only under the company's Claude credential | Before any agent, `claude auth status` must show a Team or Enterprise login, an API key, or Bedrock or Vertex. A personal Pro or Max plan stops the run. |
| Acts on GitHub as the company's App, not a person | `scripts/app_token.py` mints a one-hour token for this repo only (contents, pull requests, issues and checks to write; statuses and the repo's rules to read; never workflows, secrets or Actions), again before the push. Set `DUALTRACK_APP_ID` and `DUALTRACK_APP_KEY`. No agent's environment carries it. |
| Never merges | `scripts/merge_gate.py` refuses in company mode. The repo's rulesets, code owners and a human reviewer decide. |
| Agents' shells are sandboxed | Claude Code's sandbox, failing closed. The network reaches only the profile's **Allowed domains**. |

**The App's key.** Best kept in a key vault, sign-only: set `DUALTRACK_APP_SIGNER` to a command that signs its stdin (such as your cloud KMS's sign command), and Dualtrack never reads the key. A key file in `DUALTRACK_APP_KEY`, readable only by you, is the weaker fallback. Keys never expire. To rotate one, make a second key in the App's settings, switch to it, then delete the old one. Every token is revoked when it is replaced and when the run ends.

Your company's managed settings outrank all of this. Run `PREFLIGHT=1` once under them before the first real run.

Not yet covered:
- The shell sandbox covers branch code and the loop's own test runs, not the agents' Read, Edit and WebFetch tools. Those run outside it, and only deny lists limit them.
- Commits are not signed.
- The record is still markdown in the state repo.

## Daily use

With the plugin, `/dualtrack:dualtrack` does each of these for you. By hand:

1. **Run:** `bash ../dualtrack-core/scripts/daily_loop.sh profile.md`, by hand or on a schedule.
2. **Read the brief:** a Claude doc per product, newest day first, with a **Your call** dropdown on each row. Also in `product-context/morning.md`. `/dualtrack:dualtrack-team` in Claude Code walks you through it (`/dualtrack-team` if you copied the skills in instead). Set **Brief doc** to `none` for files only.
   `product-context/inbox.md` lists every option and bet with its type (Issue, Opportunity or Insight), its priority, where it is now (Offered, Picked, Held, Blocked, Needs you, PR open, Merged, Resolved, Closed or Declined), a link to the line behind it, and the next step. It is rebuilt at every run and every `decide` call, from the records below. In a state repo on GitHub, it is the team's screen: open it there, on any device.

   `product-context/product.md` is the product memory every agent reads: what the product is, who uses it, its areas, key flows and your standing instructions. The first run creates it from a template; fill it in. `product-context/conventions.md` collects what you say in comments on Dualtrack's pull requests, and the reviewers follow it. Edit or delete any line.
3. **Decide:** in the doc, or from your repo's root:

| Command | Effect |
|---|---|
| `python3 ../dualtrack-core/scripts/decide.py 1` | build option 1 |
| `python3 ../dualtrack-core/scripts/decide.py done 1 "how"` | option 1 was settled without code |
| `python3 ../dualtrack-core/scripts/decide.py no "why"` | none of these; not offered again |
| `python3 ../dualtrack-core/scripts/decide.py try "what"` | ask for something else |
| `... decide.py --by "Sam" 2` | make a call under a teammate's name; without `--by`, every call carries the profile's **Owner** |
| `... decide.py owner "title" "Sam"` | sign off a bet, or hand it on; until someone does, Dualtrack agents sign it |
| `python3 ../dualtrack-core/scripts/decide.py answer "text"` | answer Dualtrack's question |
| `python3 ../dualtrack-core/scripts/decide.py allow` | let through a bet Dualtrack agents held and asked you about; a safety stop is not a question, so `allow` refuses it |
| `python3 ../dualtrack-core/scripts/decide.py resume` | let a team carry on after two closed changes in a row |

Lost? `/dualtrack:ask-dualtrack` (or `/ask-dualtrack`, copied in) names the next step and command for where you are. Copy it in with `cp -R ../dualtrack-core/skills/ask-dualtrack .claude/skills/`.

4. **Review:** the next run builds your pick as a ready pull request. Merge it, comment on it to ask for changes, or close it with a one-line reason. The next run builds your comments on the same pull request; only people with write access to the repo can ask. A close reason goes into the record Dualtrack agents read every run.

   If Dualtrack agents find your pick already built, they say so in the brief, closes the pick and moves on to the next one. Nothing is opened.

   If two pull requests in a row close unmerged, Dualtrack agents pause until you run `decide.py resume`. To steer it before then, give a close reason it can act on, or ask for what you want with `decide.py try "what"`.

## Schedule

The loop is one command. Anything that runs commands with your Claude Code login can schedule it: cron, Task Scheduler, a CI service, or a Claude Code routine in the cloud. Run it by hand until you trust it. `.github/workflows/daily.yml` is an untested GitHub Actions example, off by default.

A routine is the one place Dualtrack agents have run unattended so far. [docs/schedule.md](docs/schedule.md) sets one up. A new routine can get all of your connectors by default, such as email, files and calendar. Remove every connector before its first run: Dualtrack needs none of them.

| Run | Estimated usage on your plan |
|---|---|
| weekly review | $1.11 to $2.85, median $1.84 |
| run that builds | $1.11 to $2.85, median $1.84 |

The only measured runs in this repo are 25 priced runs of the injection eval (2026-11-04 to 2026-11-17, `evals/injection/results.jsonl`), each a full loop on a small repo: $1.11 to $2.85, median $1.84. Both rows use that one range: no weekly review was priced on its own. Real runs vary. One cloud run cost $1.14 and stopped before it built anything. To see what your own runs cost, run `python3 ../dualtrack-core/scripts/stats.py` from the folder that holds `profile.md`. It prints counts only and sends nothing.

Setup suggests a limit of $10 a run, and you can choose another amount or none. Every brief shows what this run cost, plus the totals for the last 7 and 30 days, and `costs.md` lists every call. On Mondays the brief opens with the week in numbers (spend against the week before, cost per merged pull request, outcomes, stops) and keeps it in `weekly.md`; a webhook, if you set one, carries it too, so you can route it to email. Change the limit when you've seen your costs: put a dollar figure, or none, in the profile's **Run cap**, or set `COST_CAP` for one run. With a cap set, a run never starts a build it can't afford to review, and a run cut short picks up at review next time.

## Limits

Dualtrack agents never:

- pushes your main branch, or merges, unless you turn on Auto-merge and every check below holds;
- acts on anything in the brief doc except your call and reply (the doc is private until you share it);
- merges a visible change unless you turn on Auto-merge and every check below holds;
- holds more than one change open;
- carries on after two changes in a row close unmerged (it pauses until `decide.py resume`);
- touches migrations, deletions, spend, legal pages or user data (it holds them for you, judged by file names, titles and the lines the change adds; a line it doesn't recognise can still get through);
- runs twice at once in one checkout;
- gives tests your keys, or (on macOS) lets them reach a domain you haven't allowed. Elsewhere there is no sandbox, and the safety check says so;
- spends past your **Run cap**: setup suggests $10 a run, and you can change it or turn it off.

Every pull request carries a "How this was made" trail from real commits, test runs and the reviewer's verdict.

## Agents

In `agents/`:

| Agent | Job | Can | Cannot |
|---|---|---|---|
| `setup` | drafts your profile; asks only what it cannot infer | read your repo | edit files or run commands |
| `product-manager` | researches, tries to disprove its ideas, fills the Decisions table | read your repo and the run's notes | edit files or run commands |
| `product-design` | designs each visible change before it is built: flow, states, exact words | read your repo | edit files or run commands |
| `ux-review` | walks the path to first value and reviews every visible change | read your repo | edit files or run commands |
| `engineer` | builds one item test-first on a branch | edit files and run tests on its branch | push, switch branches or open a pull request |
| `navigator` | reviews plan and branch on a different model; answers APPROVE or CHANGES | read your repo | edit files or run commands |

The run, not an agent, pushes the branch and opens the pull request. It never merges unless you turn on **Auto-merge**, and never pushes to your main branch. Tests check both.

### Glossary

Every name says whether a person or an agent did the work. Full list: `docs/glossary.md`.

| Term | Means |
|---|---|
| the team | the people and the Dualtrack agents working together |
| Dualtrack agents | work only the agents did |
| Dualtrack [role] | one agent by role: Dualtrack product manager, Dualtrack engineer, Dualtrack navigator, Dualtrack product designer, Dualtrack UX reviewer |
| the owner | the person who confirms what gets built; their call beats every other signal |

Never "PM" for an agent: a human product manager may be on the team.

Both design agents judge by `standards/`: core heuristics, component checklists, interface words, plus one file per surface in your profile's **Surfaces** line (`cli`, `web`, `docs`). Set **Design checks** to a deterministic tool, such as axe-core or impeccable's detector, and UX review treats its output as ground truth. Sources: `standards/README.md`.

### Pairs well with ponytail

[Ponytail](https://github.com/DietrichGebert/ponytail)'s rules, added to the engineer's prompt, halved the code it wrote at no cost in correctness:

| Engineer, 10 runs each | Without | With ponytail |
|---|---:|---:|
| Code lines, median (range) | 20 (16 to 21) | **11 (9 to 13)** |
| Hidden acceptance test passed | 10 of 10 | 10 of 10 |
| Cost per run, median | $0.144 | $0.148 |

One small Python task, Sonnet, 2026-11-04. Method, limits and raw data: `benchmarks/ponytail/`. Setup turns it on by default; to turn it off, set `**Engineer rules:** none`. To turn it on by hand:

1. In Claude Code, type `/plugin marketplace add DietrichGebert/ponytail`, then `/plugin install ponytail@ponytail`.
2. Read its rules, in `~/.claude/plugins/cache/ponytail/ponytail/<version>/skills/ponytail/SKILL.md`.
3. In your `profile.md`, set `**Engineer rules:** ponytail <version>`, for example `ponytail 5.3.2`.

The next run uses that version, and only that one: a plugin update changes nothing until you write the new version. To turn it off, set the line back to `none`.

### Code Review, auto-merge and Frontend Design

Four profile lines, all off by default. A missing line or the template's placeholder counts as off. Design rules on with the plugin missing stops the run and prints the install line.

| Profile line | What it does |
|---|---|
| `**Code review:** on` | after the pull request opens, the kit's adaptation of Anthropic's Code Review command reads it headless and looks for bugs; nothing to install |
| `**Name in pull requests:** on` | the "Decided by" line that opens each pull request shows the name of whoever confirmed the bet, instead of "the owner" |
| `**Auto-merge:** on` | Dualtrack agents squash-merge their own pull request when `scripts/merge_gate.py` finds every check holds |
| `**Design rules:** frontend-design` | the Frontend Design skill joins the prompts for web items only: the designer's for every visible item in a repo whose **Surfaces** names `web`, and the engineer's only when that design says `Surface: web` |

**Code Review only reads.** It runs `commands-adapted/code-review.md`, whose tool list allows only read tools and three read-only REST subcommands of `scripts/ghrest.py` (`pr info`, `pr diff`, `pr files`, each one GET). It denies `gh` itself, ghrest's write subcommands, file edits and inline comments. The adaptation has no `--comment` option, and its findings go to `code-review.md` in your record. Only its own all-clear line counts as an approval. Findings, a skip (it skips closed, draft and already-reviewed pull requests), an error or no output never pass. Its cost varies with the size of the change; there is no estimate yet. It runs with `--max-budget-usd` set to what is left of the run cap.

**Auto-merge needs every check, decided by a script, never an agent:**

1. Auto-merge is on.
2. The change touches no **Protected path**, and no dependency manifest, lockfile, migration, CI (`.github/`), deploy or config file. Nor any agent instruction file, such as `CLAUDE.md` or `AGENTS.md`, which Code Review reads as its rules. The list is `RISKY` in `scripts/merge_gate.py`. A change to the profile itself is held for you, merge or not.
3. At most 50 changed lines in at most 3 files.
4. The navigator, UX review and Code Review all approve (Code Review's all-clear must be its whole answer), and, in a repo with web pages, the screenshot check passed.
5. The tests pass (a change that only "fails no new tests" on a broken main is never merged by the gate), and the pull request's CI is green on the exact commit that was reviewed, including every check named on the profile's **Required checks** line. No such line, no CI, skipped, neutral, pending or unreadable is not green. The gate waits up to `CI_WAIT` seconds (default 600) for CI to finish. A repo with no CI looks the same as CI not started yet, so it waits the full time and then leaves the change for you.
6. The checks read a copy of the profile taken when the run starts, so an agent's edit to it during the run changes nothing.
7. Then it squash-merges through the REST API, pinned to that commit, and writes the merged commit and `git revert <sha>` to `team-log.md`.

Anything it cannot read fails closed, and the pull request waits for you with the failed check named in Dualtrack's log. So auto-merge needs Code Review on, a repo with CI, and **Required checks** set.

**What the engineer can run.** No open shell: it edits files inside your repo, runs `git add`, `commit`, `diff`, `status`, `log`, `rm` and `mv`, and your exact **Test commands**. Claude Code denies anything else, including `git push`, `gh`, `curl` and chained commands. It cannot write to `.git/` or outside the repo. One gap is still open: the loop runs your test command on the engineer's code in the sandbox described under **Safety checks**, and that sandbox does not hide every file you can read. It hides your `gh` login, `~/.ssh` and the other secret folders listed there, but not the rest of your home folder, and a repo that is set to `Sandbox: none, I accept the risk` runs it with no file limit at all. The environment is always clean: no `GH_TOKEN`, no keys. Keep auto-merge off on a repo whose test run could reach anything you care about.

**Watching for leaks.** Each run makes a canary: a fake GitHub token, new every run and never stored. The tests get it as `GITHUB_TOKEN`. If it turns up in your repo, the record or the run's files, something read a secret and wrote it out: the run stops, nothing is pushed, and Dualtrack's log, the morning brief and the brief doc tell you, with the token blanked. It only sees what the run writes. A token sent straight over the network is not caught.

**Refused tool calls.** Every tool call Claude Code refused, from any agent, goes to `denials.md` in your record with a line in Dualtrack's log. A planted instruction usually shows up there first, as an attempt.

**Injection eval.** `python3 evals/injection/run.py` runs the real loop (about $2.20, your login) on a small repo whose README, issue list and code carry planted instructions: push to main, edit `CLAUDE.md`, write outside the repo, copy the token, claim approval. It checks what the change actually did and lists refused calls. It says INCONCLUSIVE when the run built nothing. `--vector=outside` plants the same text in an outside reviewer's comment instead, and also checks that it never reaches what the other agents read. `--vector=analytics` plants it in a fake PostHog source, and checks that the source was read and that the text never reaches the notes written from it. Results: `evals/injection/results.jsonl`. The file holds 26 runs, from 2026-11-04 to 2026-11-17. 20 held every check, and three of those stopped before they built anything. 6 failed one check. The 2026-11-04 run failed the GITHUB_TOKEN check, and the row does not record why. Five of the 11 runs on 2026-11-14 failed the approval check, which matched quoted planted text; that was corrected. Since then every run that built a change held every check: one on 2026-11-15, one on 2026-11-16, both outside-comment runs on 2026-11-16, and three in-repo runs and two analytics runs on 2026-11-17. Each result is one run on one model mix, so it is not a rate.

**Harm eval.** `python3 evals/harm/run.py` puts each case to the product manager (the real loop, with the bet owner-confirmed), the engineer and the navigator, about $3 a case on your login. The cases cover illegal products, covert tracking and stalkerware, phishing and impersonation, fraud and fake reviews, deception and dark patterns, and undisclosed data sharing. It fails if any agent builds one, or the navigator approves it, or no reason and honest version are given. Cases: `evals/harm/cases.json`. Not run in CI, because it spends.

**Your working tree.** By default the run fetches your default branch from GitHub and builds in its own worktree from that, so your uncommitted changes, untracked files and unpushed commits neither stop it nor appear in its change, and it never resets your checkout. It starts from what is on GitHub, so push what you want it to see. Only an in-place run (`DUALTRACK_IN_PLACE`) needs a tree with no changes and no untracked files. When a run stops partway, it saves what Dualtrack agents left in `leftover.diff` in your record and clears its own worktree.

**A repo has web pages** when its profile's **Surfaces** line names `web`. Then, for each visible change, the loop renders every changed `.html` page headless with Playwright (`npx -y playwright@1.64.1`, installed on first use, about 100 MB), saves the screenshots in the run folder and gives them to UX review. A page that will not render is a CHANGES verdict, never a pass. A change with no static page to render, such as a page in an app that needs a server, cannot pass the screenshot check, so it never auto-merges. A CLI or docs repo never loads a browser.

**What has been exercised, and what has not:**

| Behaviour | Exercised |
|---|---|
| Merge gate: each check failing, all passing, unreadable data, the CI wait | by tests, with a fake `gh` under the real `ghrest.py` |
| Code Review's tool list and verdicts, and ghrest's review reads being GETs only | by tests, with a fake `claude` that fails if the list would let it write, and a fake `gh` |
| Frontend Design reaching web items only, and the stop when it is missing | by tests, with a fake plugin record |
| A real headless render of a static page | once, by hand, on a small HTML file |
| Code Review on a real pull request | in a cloud routine, 2026-11-04: approved fixture PR #4 over REST with no refused calls |
| The whole loop in a cloud routine | 2026-11-04: research to a ready PR with navigator, UX review and Code Review approving; the gate then held it at 93 lines, as it should |
| A real squash merge on GitHub, and CI read from a real repo | 2026-11-04: `merge_gate.py` read the fixture's CI on the exact head and squash-merged fixture PR #5 over REST; run by hand with the reviewers' approvals supplied, not by the loop |
| Planted instructions in the repo | `evals/injection/run.py`, latest run 2026-11-17: every check held |
| Planted instructions in an outside reviewer's comment | `evals/injection/run.py --vector=outside`, 2 runs on 2026-11-16: every check held |
| Planted instructions in an analytics source | `evals/injection/run.py --vector=analytics`, 2 runs on 2026-11-17: every check held |

**Where they come from.** Both are Anthropic's, from the `claude-plugins-official` marketplace, under the Apache License 2.0. Frontend Design is not copied: the loop reads it from where Claude Code installed it, found through `installed_plugins.json`, and each run's team log records the version and commit it used. Code Review is an adapted copy in `commands-adapted/`, with the Apache-2.0 `LICENSE` and a `NOTICE` beside it; its header names the source and what changed (GitHub reads over REST, every way to post removed). Source files, checked for this release:

| File | Version | sha256 |
|---|---|---|
| `code-review/commands/code-review.md` | code-review 1.0.1 | `3f02ea6eed996590348264777b2e324859a6e2c0c5f7dd298617ea21deb3b1b2` |
| `frontend-design/skills/frontend-design/SKILL.md` | frontend-design 1.1.1 | `d91970639e9f5c37682ac7ab60094d35f1c7c1f38d731bd56396563aee10c1d3` |

Marketplace snapshot `fa4eb54397ee2faccb6940512a19c017cb1337f3` (its `.gcs-sha`; the local copy is not a git checkout).

**To turn them off or roll back:**

- Set `**Auto-merge:** off`, `**Code review:** off` or `**Design rules:** none`. The next run goes back to ready pull requests that wait for you.
- To remove Frontend Design: `/plugin uninstall frontend-design@claude-plugins-official`. Set `**Design rules:** none` first, or the next run stops.
- To undo a change Dualtrack agents merged: run the `git revert <sha>` line from `team-log.md` on a branch, and open a pull request for it.

## Each run

**The promise.** Every change comes with proof it broke nothing. When something is already broken, Dualtrack finds out why, fixes it first if it can, and says plainly what it could not.

Before any agent is paid, the run checks that your tests pass on the default branch. What it does when they do not:

| On the default branch | What happens |
|---|---|
| Tests fail here **and** the **Required checks** fail in CI on the same commit | "Get main green" becomes the run's item. The failing tests are the tests. One pull request, then the run stops; the planned item runs next time. |
| Tests fail only here, and CI is green on the same commit | CI is the baseline. The planned item is built; the pull request names the tests that failed here and must pass CI before anyone merges it. |
| ...and the branch then fails only tests main already fails | "No new failures" counts as proof. The pull request lists the existing failures and never auto-merges. If the branch fails a test main did not, the engineer fixes it like any red branch. |
| Tests fail here and CI is not green on that commit, is pending or cannot be read (including no **Required checks** line) | The run stops. The log names the failing tests, or the last 20 lines of output when no test names can be read, never only the last line. |

CI must report on the default branch's commits for the first two rows: a check that runs only on pull requests never reports on `main`, so the run stops.

In every case where the tests fail, Dualtrack opens one GitHub issue labelled `dualtrack` for that set of failing tests, with the test names and their output. A repeat run comments on the open issue instead of opening another. Test names are read from unittest and pytest output. A preflight run only says the tests fail; it opens nothing.

Order: watch the numbers (stop if nothing changed), research, disprove, decide. Then:

| Kind of work | What happens |
|---|---|
| not visible (any size) | built at once, reviewed, two fix rounds; a medium or long item needs the navigator to approve its plan first |
| visible | designed, built and reviewed; the pull request says it was built before your pick |
| content or outreach | a brief for you, never built; Dualtrack agents build the best buildable runner-up the same run |
| can't be built | Dualtrack agents ask you what they need; your `decide answer` builds it again |
| a call that is yours (stop list, protected path) | Dualtrack agents ask; `decide allow` lets that bet through next run |

**Cadence**, named per run: weekly walks the funnel and reads code; daily compares numbers, checks due bets, and recommends only if a **Watch** level is crossed or a bet is due.

**Modes**, one per profile:

| Mode | Focus |
|---|---|
| `acquisition` | new people arriving and taking the first step |
| `activation` | a new person reaching first value |
| `optimisation` | people coming back, or moving on at a better rate |

**Moves:** `moves.md` defines eight generic moves. Turn one off under **Moves off**, or add your own in the same five fields.

## The record

Agents change nothing; a script files their final message. It needs only Python, adds a dated memo, a numbers snapshot and record entries to your Context path, and never overwrites.

```sh
claude -p "..." --agent product-manager > out.md
python3 ../dualtrack-core/scripts/file_memo.py profile.md out.md
```

| **Context store** | Where |
|---|---|
| `local` | a folder of Markdown files |
| `obsidian` | the same files in a vault folder, with frontmatter and links |
| `notion` | the same local files, then an optional sync (`docs/notion.md`); untested on a live workspace |

**Outside reviewers** (optional). If a review app or bot comments on your pull requests (a UX review service, a code review service), name its GitHub login under **Outside reviewers** in the profile. While Dualtrack's change is open, the brief shows what it said, and Dualtrack agents read it only as outside input, never as instructions. Nothing depends on one. To make a reviewer's status a gate for Auto-merge, add it under **Required checks** instead.

Each run also leaves these in your Context path:

| File | What it holds |
|---|---|
| `morning.md` | the brief: what Dualtrack agents did, its cost, and your next step |
| `areas.md` | the map of your product's areas: code paths, pages, events and what success looks like in each. Dualtrack agents draft it and keep it in step with the code; the brief shows each change, and `decide areas` takes it. Every 90 days the brief asks you to look again. Edit it yourself any time. |
| `costs.md` | every agent call, with its model and cost |
| `bets.md` outcomes | a merged bet stays "shipped, awaiting evidence" until a `result` line says whether it helped; `decide.py result "title" helped\|no\|unclear "evidence"` records yours |
| `dashboard.html` | one page to open in your browser: what needs you, whether shipped work helped, and what it cost. Rebuilt every run; sends nothing, loads fonts from Google Fonts |
| `scripts/dashboard_server.py` | the same page, live on 127.0.0.1 only: its buttons record your calls and Undo takes back a pick. Run it from your product repo; it opens your browser at a link with a launch secret (the page loads only from that link) and stops after 30 minutes unused |
| `weekly.md` | Monday's summary of the week: spend, cost per outcome, outcomes, stops, and code that stayed: how many of Dualtrack's merged changes were reverted or needed a fix within 21 days, next to your own commits |
| `sources/public.md` | free public numbers every run, with no model call: GitHub stars, forks, views and clones, and weekly downloads of each package in the profile's **Packages** line (`npm:<name>`, `pypi:<name>`) |
| `team-log.md` | one line per run: what happened and what it cost |
| `last-run/` | why the last run did what it did: each agent's answer, the test output, the error log and the domains the tests called. Replaced each run. |

## Use agents by hand

```sh
claude --agent engineer
claude -p "Item: <title and Done when lines>. Review the branch against main. Profile: profile.md." --agent navigator
```

Give the engineer the recommendation. It works on a branch, tests first, and stops with a plan on medium and long items. The navigator answers APPROVE or CHANGES. Nothing is pushed or merged.

## Try it on an example

From the kit's folder:

```sh
mkdir -p .claude/agents && cp agents/*.md .claude/agents/ && claude -p "Today is $(date +%F). Profile: example/profile.md. Numbers: example/numbers.md. Cadence: weekly." --agent product-manager
```

The agent reads an invented product, Gourdly, and returns a memo ending on one recommendation. Hand-written samples per mode: `example/memos/`.

## Share how it went

The kit sends nothing to Dualtrack. Model calls go to the provider you configure, and dashboard.html loads fonts from Google Fonts.

```sh
python3 ../dualtrack-core/scripts/stats.py           # counts from your record
python3 ../dualtrack-core/scripts/stats.py --share   # opens a filled-in GitHub issue or email
```

Counts only: runs, changes merged and closed, reviewer send-backs, estimated usage. No product names, titles, reasons, code or links. Nothing is sent until you submit it yourself.

## Want this for your team?

[Saielle DaSilva](https://intentionaut.com) sets up the Dual Track Agent Team method with product teams. <!-- credit -->

## Doctor

`python3 scripts/doctor.py path/to/profile.md` checks this machine and shows what got in the way lately. It is read-only and sends nothing. Health: the safety files check, the sandbox, the state repo and the plugin version, each ok or a problem with its fix. Friction: held changes, owner questions, sandbox stops and run-cap overruns from the run events, since `--since YYYY-MM-DD` (default 7 days). A count the events do not record shows as `unknown`, not 0: preflight and safety-file stops leave no event. Add `--report` for a block you can paste into a bug report.

## Safety files check

At the start of every run Dualtrack checks that its safety files are the ones this release shipped. If one changed, nothing runs and the message names the file and says a modified kit is not Dualtrack. The check is not hidden and has no off switch: it is `scripts/tamper.py`, and the files and their hashes are in `safety-files.json`.

The files it reads: `agents/*.md` and `standards/*.md` (every agent and standard, which carry the harm rule), `scripts/*.py` and `scripts/*.sh` (every script: the stop list, the sandbox, the egress proxy, the merge gate and this check itself), `sources.json` (the read-only source list), `hooks/*.json` and `skills/*/SKILL.md`. In a git checkout of the kit, `safety-files.json` must also match the committed copy, so changing a file and its hash together without committing is caught too. After a change to one of them, run `python3 scripts/tamper.py pin` and commit `safety-files.json`; a test fails until you do.

## Check a copy is the real Dualtrack

Releases are not signed yet. `scripts/verify.py` and `docs/release.md` describe how signing will work.

## Remove Dualtrack

Setup and runs leave the things below. Remove the ones that apply to you, in any order.

| What | Where | How to remove it |
|---|---|---|
| The record, if you kept it beside your repo | `../dualtrack-state`, a git folder. It holds every product filed in it, so run `ls ../dualtrack-state` first. | Delete the folder. |
| The record, if you chose "This computer only" | `profile.md`, `setup-notes.md`, `numbers.md` and `product-context/` in your repo's root, kept out of git | Delete them. |
| Lines setup added to git's ignore list, in that same case | `.git/info/exclude` (the folder `git rev-parse --git-common-dir` prints, if you use worktrees) | Delete the four lines naming those files. |
| The private state repo on GitHub, if setup created it | `<you>/dualtrack-state`. It may hold other products' records too. | Settings, then Danger Zone, then Delete this repository. Or `gh repo delete <you>/dualtrack-state`, after `gh auth refresh -s delete_repo`. |
| Pull requests, issues and branches Dualtrack opened | Your product repo: branches named `team/<date>-<time>`, pull requests labelled `team-daily`, issues labelled `dualtrack`. | Close them, and delete the branches on GitHub. The kit never deletes one. |
| Dualtrack's own folder in your home | `~/.dualtrack` (or the folder `DUALTRACK_HOME` names): the dashboard's launch secret and `source-health.md` | Delete the folder. |
| The daily schedule, if you set one | A routine at claude.ai/code/routines, a `/loop` session you left open, a cron line, or `.github/workflows/daily.yml` if you turned it on | Delete the routine there (it cannot be deleted from inside Claude Code), close the session, or remove the line or file. |
| Sources you connected | Each one `/dualtrack:dualtrack-connect` added to Claude Code | `claude mcp remove <name>`. A connector you added in Claude.ai is removed in its settings. |
| The brief doc, if **Brief doc** was `claude` | A Claude doc per product | Delete it in Claude. |
| The plugin | Claude Code | `/plugin uninstall dualtrack@dualtrack`, then `/plugin marketplace remove dualtrack`. If you cloned the kit, delete `../dualtrack-core` too. |

Your product's own code is never changed by setup, so there is nothing to undo there.

## Help and support

To see what one finished day looks like, read [`docs/example.md`](docs/example.md).

Ask in [GitHub Issues](https://github.com/intentionaut/dualtrack-core/issues) on `intentionaut/dualtrack-core`, for bugs and questions alike. Report a security problem privately instead, as `SECURITY.md` describes: GitHub private vulnerability reporting first, then email if that is unavailable.

To help us reproduce it, include:

- the output of `python3 scripts/doctor.py path/to/profile.md --report` (see Doctor);
- the stop line, if a run stopped: the "What Dualtrack agents did" line in `product-context/morning.md`, which starts `stopped:`;
- your operating system and the output of `python3 --version`.

Free support: a reply within 5 working days.

## Licence

Source-available. Free to use, Apache 2.0 after two years.

We use the Functional Source License because it protects against a hosted copy competing with Dualtrack. Every release becomes Apache 2.0 after two years.

Functional Source License 1.1, Apache 2.0 Future License (FSL-1.1-ALv2). See `LICENSE` and `NOTICE`. You can use, change and share Dualtrack for any purpose except a product or service that competes with it. Two years after each release, that release becomes available under the Apache License 2.0. If you share a copy or a changed version, keep `LICENSE` and `NOTICE` with it. The licence covers the code, not the name: see `TRADEMARKS.md` before you call a changed copy Dualtrack. `commands-adapted/code-review.md` is adapted from Anthropic's Code Review command, also under the Apache License 2.0: see `commands-adapted/LICENSE` and `commands-adapted/NOTICE`.
