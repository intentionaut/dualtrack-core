# Integrations plan

Status, 2026-11-06: sources are built. Pendo, PostHog, Mixpanel, Jira, Usersnap, Confluence, Amplitude, Intercom, Figma, Notion, Linear, Google Drive, Sentry, BigQuery, Dovetail, Gong, ProdPad, Asana, ClickUp, Canny, Statsig, Datadog, HubSpot, LaunchDarkly, Optimizely, Monday.com, Cloudflare, Search Console and Checkly (added 2026-11-16) are in `sources.json`, each with only read-only tools, checked by `scripts/sources.py check` and its tests. Slack is not built yet.

| Source | Server | Read-only how | State |
|---|---|---|---|
| Pendo | `app.pendo.io/mcp/v0/shttp` (and regional) | read tools only; write tools are an admin opt-in | built; visitor- and account-level tools left out (personal data) |
| PostHog | `mcp.posthog.com/mcp?mode=tools&tools=<the read tools>` | server exposes only the listed tools; all read-only in PostHog's schema | built, names checked 2026-11-06 |
| Mixpanel | `mcp.mixpanel.com/mcp` | allowlist | built |
| Jira | `mcp.atlassian.com/v2/mcp` (Atlassian Rovo) | allowlist; admin grants read groups only | built |
| Usersnap | `mcp.usersnap.com/mcp` | allowlist; switch off the 2 write tools | built |
| Confluence | `mcp.atlassian.com/v2/mcp` (same as Jira) | allowlist; admin grants read and search groups only | built; personal spaces and page permissions left out |
| Amplitude | `mcp.amplitude.com/mcp` (EU variant) | project role Use MCP (read), plus allowlist | built; user profiles, session replays and mixed read-write tools left out |
| Intercom | `mcp.intercom.com/mcp` (EU variant) | allowlist; no read-only mode | built: articles and companies only; contacts and conversations left out (personal data) |
| Figma | `mcp.figma.com/mcp` (or desktop `127.0.0.1:3845`) | allowlist | built |
| Sentry | `mcp.sentry.dev/mcp` | allowlist, names from Sentry's own repo | built; user reports, replays, breadcrumbs, tag values, attachments and Seer left out |
| Notion | `mcp.notion.com/mcp` | allowlist of read tools, from the live server | built; members, guests, memory and meeting notes left out |
| Cloudflare | `graphql.mcp.cloudflare.com/mcp` | GraphQL API has no mutations; allowlist from Cloudflare's repo | built; read live 2026-11-06; deprecated by Cloudflare, its replacement can write |
| Search Console | `uvx mcp-search-console` (community, MIT) | `webmasters.readonly` scope plus allowlist; sitemap and site writes left out | built; read live 2026-11-06 |
| Google Drive | Claude.ai's own connector (`claude_ai_Google_Drive`) | allowlist | built; sharing details left out. Works only under a claude.ai login, not an API key |
| BigQuery | `bigquery.googleapis.com/mcp` | `execute_sql_readonly` (SELECT only), dataViewer on chosen datasets, IAM deny on `execute_sql` | built; point it at aggregated datasets |
| Dovetail | `dovetail.com/api/mcp` | allowlist; no read-only mode | built: project and tag structure only; research data, highlights, people, docs and files left out |
| Gong | `mcp.gong.io/mcp` | read-only by design; `mcp:read` scope | built, opt-in only with the privacy team: answers draw on named calls; `generate_brief` left out; uses Gong credits |
| ProdPad | `api.prodpad.com/mcp` | allowlist; no read-only mode | built: roadmap, OKRs and ideas; feedback and search left out (customer contacts) |
| Asana | `mcp.asana.com/v2/mcp` | allowlist; no read-only mode | built; users, comments, notifications left out |
| ClickUp | `mcp.clickup.com/mcp` | allowlist; no read-only mode | built; members, chat, comments, time entries left out |
| Canny | `api.canny.io/api/mcp/v1` | allowlist; no read-only mode | built; users, voters, comments, insights left out |
| Statsig | `api.statsig.com/v3/mcp` | read-only Console API key, plus allowlist | built; generic log and API reads left out |
| Datadog | `mcp.datadoghq.com/v1/mcp` (and per site) | admin leaves MCP Write Access off | built; RUM, users, audit events left out |
| Checkly | `api.checklyhq.com/mcp` | allowlist; no read-only mode, so grant read permissions only | built 2026-11-16, names from Checkly's tools page; not yet read against a live account. Members, alert channels, environment variables and result files left out |
| HubSpot | `mcp.hubspot.com` | allowlist; no read-only mode | built: campaign and content analytics only; contacts and CRM records left out |
| LaunchDarkly | `mcp.launchdarkly.com/mcp?writes=none` | `writes=none` hides writes; a read-only role enforces | built: flags, experiments, releases, incidents; contexts, sessions, members, segments, keys left out |
| Optimizely | `exp.mcp.opal.optimizely.com/mcp` | allowlist; no read-only mode | built; the lifecycle write tool left out; needs Mark |
| Monday.com | `mcp.monday.com/mcp` | allowlist; read-only flag is local-only | built: boards, schemas, insights; people columns, users and updates left out |
| Linear | `mcp.linear.app/mcp/readonly` | the vendor's read-only endpoint; every tool on it allowed | built |

**Live checks, 2026-11-06.** Every built source's URL answered as an MCP server: 401 with a Bearer sign-in challenge, or a completed handshake (BigQuery, ProdPad). Usersnap's URL now ends in `/mcp/`, as the server redirects there. Tool names checked against a live server: Notion (8 of 8), Google Drive (5 of 5), BigQuery (7 of 7). Every other allowlist comes from the vendor's docs and is confirmed at the first sign-in.

Headless runs can't sign in to OAuth servers. Run `claude mcp login <name>` once in a terminal; Claude Code stores and refreshes the token.

Two kinds, because they carry different risk:

- **Sources** read data in. Read-only, through MCP.
- **Slack** sends the brief out. It is a send in the owner's name, so the owner sets it up once.

## 1. Sources

### Shape

One contract for every platform. A source is an entry in `sources.json` in the kit:

```json
{"posthog": {"server": "posthog", "tools": ["mcp__posthog__query-run", "mcp__posthog__insights-get-all"],
             "ask": "Weekly active users, the activation funnel and the top 5 drop-off steps, last 14 days."}}
```

The profile names which ones to use: `**Sources:** posthog, ga4, sentry`.

### Run

1. A new `fetch` step runs before research, one `claude -p` call per source.
2. `--allowedTools` is only that source's listed tools, with `--permission-mode dontAsk`. Nothing else runs, writes or sends.
3. It writes `$CONTEXT/sources/<name>.md`. Every number carries its query and time window.
4. The product manager reads those files beside the numbers file. The numbers file stays, for anything pasted by hand.
5. A source that fails says "posthog: could not be read" in the brief. Never "no data".

### Receipts

Each option in the brief cites the lines behind it: source file, query, window. An option with none says "no evidence yet". The kit collects no user behaviour itself.

### Guards

- Only tools on the list run. A write tool on a source's list fails the kit's tests (name check for create, update, delete, send).
- Credentials stay in the owner's MCP config. The kit stores none.
- Cloud routines: sources are named connectors, read-only tools only. This replaces "no connectors on routines" with "only named, read-only connectors".
- Source text is data. It goes to the agents inside the same wrapping as other untrusted input, and the injection eval gets a planted instruction in a source file.

## 2. Slack

### Phase 1: the brief arrives in Slack

- An incoming webhook for one channel the owner picks. A webhook can post to that channel and nothing else, and reads nothing.
- The webhook URL lives in the owner's environment (`DUALTRACK_SLACK_WEBHOOK`), never in the profile or repo.
- The post: goal, each option with its receipt, cost, and the pick command.
- The canary check runs on the post before it sends. A post holding the canary is not sent.

### Phase 2: pick from Slack

Buttons ("pick 1", "pick 2") need a Slack app and a server to receive the clicks. That is hosting and a new attack surface. Do it only after phase 1 is used for two weeks.

## Order

1. Source contract, fetch step, receipts in the brief, proved on Pendo. Tests plus one real run on the fixture.
2. PostHog, then Mixpanel, one config entry each.
3. Slack phase 1.
4. Other platforms in the table.
5. Slack phase 2, if earned.

Analytics order, decided by the owner 2026-11-05: Pendo, PostHog, Mixpanel.

- **Pendo**: official hosted MCP server. Read-only tools are a separate toggle (Settings > Subscription settings > AI access); write tools, currently creating feedback items, are an admin opt-in. The setup step tells the owner to leave write tools off. Tool names come from Pendo's "Pendo MCP tools for AI agents" page, not yet read.
- **PostHog**: official MCP server; tool names to read from the live server.
- **Mixpanel**: official hosted server at `https://mcp.mixpanel.com/mcp` (EU and IN endpoints exist), OAuth, in beta. It has write tools (dashboards, cohorts, flags), so the allowlist is what keeps it read-only.

## Open for the owner

- Which Pendo subscription to test against. The fixture needs one with real data, or the run proves only that the plumbing works.
- Which Slack workspace and channel for the fixture test.

## Source health

Once a day, when a Claude Code session starts, the plugin checks every source this machine has connected, in the background, with one call (about $0.002). It writes `~/.dualtrack/source-health.md`: per source, `ok`, a server that needs signing in, listed tools the server no longer offers, or new read-looking tools. Nothing is changed. A run shows any line that is not `ok` in the brief's safety checks. Tools passed over on purpose are listed under `left_out` in `sources.json`, so they are not flagged. Run it by hand with `python3 scripts/source_health.py --force`.
