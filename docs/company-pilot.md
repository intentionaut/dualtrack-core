# Try Dualtrack at your company

A first run of Dualtrack in company mode, on one internal repo. It takes about an hour, most of it waiting
for approvals. Nothing merges: Dualtrack agents open a pull request, and a person on your team decides.

## Before you start

- **Ask first.** Installing a GitHub App on a company repo usually needs an org admin. Many companies also
  need security to approve a new AI tool. Show them `README.md`'s Company mode section and this page.
- **Pick an internal repo** that no customer sees, with tests that run on a laptop and a rule on `main` that
  needs one approving review.
- **Your company's Claude login**: a Team or Enterprise seat, a Console API key, or Bedrock or Vertex.
  A personal Pro or Max plan is refused.

## 1. Create your company's GitHub App

Each company makes its own. Nobody outside your company holds its key.

1. In your org on GitHub: **Settings > Developer settings > GitHub Apps > New GitHub App**.
2. **Name** it, for example `dualtrack-<your company>`. **Homepage URL**: your repo's URL.
3. **Webhook**: untick **Active**.
4. **Repository permissions**, everything else on No access:

   | Permission | Set to |
   |---|---|
   | Contents | Read and write |
   | Pull requests | Read and write |
   | Issues | Read and write |
   | Checks | Read and write |
   | Administration | Read-only |
   | Commit statuses | Read-only |
   | Metadata | Read-only |

   Leave **Workflows** on No access. With it, a token could edit CI and reach the repo's secrets.
   No organisation or account permissions.
5. **Where can this GitHub App be installed?** Only on this account.
6. **Create**, then note the **App ID**.
7. **Private keys > Generate a private key.** Best: put it in your company's key vault and give Dualtrack a
   sign command (step 3). Otherwise keep the file where only you can read it:
   `mv <the downloaded file> ~/.config/dualtrack/app.pem && chmod 600 ~/.config/dualtrack/app.pem`
8. **Install App > Only select repositories**, pick the one repo.

## 2. Install Dualtrack

In Claude Code:

```
/plugin marketplace add intentionaut/dualtrack-core
/plugin install dualtrack@dualtrack
```

Then, in your repo, type `/dualtrack:dualtrack`. Setup asks a few questions and writes the profile. Keep
Dualtrack's record in a private repo your company owns.

## 3. Turn on company mode

Add to the profile:

```
**Company mode:** on

**Allowed domains:** <the package registry your tests need, such as registry.npmjs.org>
```

Then set, in the shell that runs Dualtrack:

```
export DUALTRACK_APP_ID=<the App ID>
export DUALTRACK_APP_KEY=~/.config/dualtrack/app.pem     # or, with a key vault:
export DUALTRACK_APP_SIGNER="<your KMS sign command, reading stdin, writing the raw signature>"
```

## 4. Check, for free

```
PREFLIGHT=1 bash <the kit>/scripts/daily_loop.sh <the profile>
```

It stops before any agent runs. Expected last line: `ready: the setup, the tests on main and the pull
requests all check out; no agent ran`. Anything else names what to fix.

## 5. Run it once

```
bash <the kit>/scripts/daily_loop.sh <the profile>
```

A run stops at the profile's Run cap: setup suggests $10, and you can change it or set none. It runs on your company's Claude account, and every brief shows what the run cost and the totals for the last 7 and 30 days.

## What to look at afterwards

- The pull request says it was opened by your App, not a person.
- `main`'s rule held: the PR can't merge until someone on your team approves it.
- In the PR, "How this was made" shows each commit, test run and reviewer verdict.
- `product-context/denials.md` lists any tool call Claude Code refused. A planted instruction would show here.
- `product-context/costs.md` has the cost of each step.

Tell us what broke, and what you'd need before using it daily.
