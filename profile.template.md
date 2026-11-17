# Product profile

**Product:** <name, and one sentence on what it does and for whom>

**Repo:** <path, or none for briefs only>

**Audience:** <who it serves, and where they already are>

**Goal:** <what growth means here: enquiries, sign-ups, revenue>

**Channels:** <what you can really use>

**Moves off:** <moves that do not fit, with why, or none>

**Constraints:** <budget, time, things you will not do, or none>

**Focus:** what the owner asked the team to look at first, in their words. It outranks Mode. Leave empty for none.

**Owner:** <the name on each bet this person picks; setup suggests your git name. A teammate can pick with decide.py --by "<name>">

**Launched:** yes | no (no while there are no users yet: the dashboard leads with delivery until there is something to measure)

**Mode:** acquisition | activation | optimisation (one, or two at once: "acquisition, optimisation")

**Funnel steps:** <arrive, take the first step, reach first value, come back>

**First moment of value:** <what a new person has to reach>

**Numbers file:** <path to the file you paste counts into>

**Sources:** <none, or any of pendo, posthog, mixpanel; connect each first with python3 scripts/sources.py setup <name>>

**Packages:** <none, or each published package as npm:<name> or pypi:<name>; its weekly downloads join the GitHub numbers in sources/public.md>

**Watch:** <number and the level that should trigger a recommendation, or none>

**Routing:** watch haiku, research sonnet, disprove opus, decide opus, review sonnet, design sonnet, engineer sonnet, navigator opus

**Context store:** local | obsidian | notion

**Context path:** <folder or vault folder for the record>

**Notion page:** <only for notion: the page to sync to>

**Surfaces:** cli | web | docs (one or more, comma-separated; each names a file in `standards/`)

**Design checks:** <optional command whose output UX review treats as ground truth, such as `npx impeccable detect src` or an axe-core run, or none>

**Engineer rules:** <none, or ponytail to have the engineer write less code (install the ponytail plugin first), or the path to your own rules file>

**Design rules:** <none, or frontend-design (install frontend-design@claude-plugins-official first)>

**Code review:** <off, or on to have Code Review read each pull request for bugs>

**Auto-merge:** <off, or on to let the team merge small, reversible changes itself>
**Name in pull requests:** <off, so pull requests say "Decided by: the owner", or on to show the name of whoever confirmed the bet>

**Company mode:** <off, or on inside a company: runs only under the company's Claude credential and a GitHub App, and never merges>

**Allowed domains:** <the domains an agent's shell may reach (company mode, or tests with Test network on), comma-separated, such as registry.npmjs.org; none by default>

**Outside reviewers:** <none, or the GitHub logins of review apps or bots whose comments on the team's pull requests you want in the brief, such as novus-by-pendo. Optional; nothing depends on one>

**Required checks:** <names of the CI checks that must pass before auto-merge, comma-separated, such as test, lint>

**Brief doc:** claude | <a Claude doc link> | none

**Settled:** <decisions not to reopen, or none>

**Rules the code must hold:** <for the navigator, or none>

**Test commands:** <how to run tests, type check and lint>

**Setup commands:** <what a fresh clone needs before the tests run, such as `npm ci`, or none>

**Setup token:** <optional: the name of one environment variable, such as `NPM_TOKEN`, passed to the Setup commands only and never to tests or agents; for a private npm registry, commit an `.npmrc` that reads `${NPM_TOKEN}`>

**Copy source:** <optional: who must write or approve copy. Leave out and the engineer writes it>

**Protected path:** <regex for files agents must not change; repeat the line for more>

**Protected text:** <file> :: <exact text that must stay; repeat the line for more>

**Limits (defaults shown, change freely):**

**Run cap:** none

**Test timeout:** 20  <!-- minutes one test or setup command may run before Dualtrack stops it and the run, with everything it started. -->

**Test network:** off  <!-- on: tests reach the internet, with no keys and the home folder closed. Add the domains they call to Allowed domains so the engineer's own test runs reach them too. Tests that need real keys run in CI only, under Required checks. -->

**Bet limit:** 3

**New idea slots:** 1

**Demand signals:** <files the new ideas step reads: positioning, offers, questions people ask>
