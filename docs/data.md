# Where your data goes

Dualtrack runs on your machine. Your code and numbers go to your model provider, inside agent prompts. The record and its pull requests stay in your GitHub. Dualtrack has no server, so nothing comes to us. What it reads, where it goes and how to turn each part off:

| What | Where it goes | Kept for | How to turn it off |
|---|---|---|---|
| Your product repo's code, issues, pull requests and their comments | Read with your `gh` login. Sent to your model provider inside agent prompts | Your provider's terms decide. Dualtrack does not know | Run Dualtrack on a repo you are happy to send to your provider |
| Comments from your **Outside reviewers** | Read by a reader with no tools. Only checked fields reach the other agents and your provider | As above | Remove the login from **Outside reviewers** in the profile |
| Numbers from your analytics sources (**Sources** in the profile) | Read through each source's read-only tools. The numbers, with their query, date range and row count, go to your provider | As above | Remove the source from **Sources** |
| Public numbers: GitHub stars, forks, views and clones, and package downloads | Fetched from `api.github.com`, `api.npmjs.org` and `pypistats.org`. No model call | In `sources/public.md`, replaced each run | Remove the **Packages** line. GitHub numbers have no switch today |
| The record: briefs, bets, decisions, costs | Written to your own state repo and pushed to your GitHub | Until you delete it. The record only grows | Not optional: it is how Dualtrack works |
| Changes Dualtrack builds | A branch and a pull request in your product repo | Until you close or delete them | Leave **Auto-merge** off (the default) and every change waits for your merge |
| `last-run/`: each agent's answer, test output, errors | Your Context path only | Replaced each run | Not optional |
| The run event (`dualtrack.run.v1`) | Your Context path. Posted to your webhook only if you set `DUALTRACK_WEBHOOK_URL` | Until you delete it | Leave `DUALTRACK_WEBHOOK_URL` unset |
| `dashboard.html` | Your machine. When you open it, your browser loads fonts from Google Fonts | Google's terms decide | No switch today |
| `stats.py --share` | Opens a filled-in GitHub issue or email. Nothing is sent until you send it | Wherever you send it | Do not run it |

Unknown: how long your model provider keeps prompts. That is set by your provider's terms and your account settings, not by Dualtrack.
