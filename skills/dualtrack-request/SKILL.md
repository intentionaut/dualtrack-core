---
name: dualtrack-request
description: Ask Dualtrack's maker for a feature, or report a gap in the kit. Drafts the request with the user, then opens a filled-in GitHub issue or email that they submit themselves. Use when the user says "request a feature", "tell the dualtrack maker", "dualtrack should do X", or "this is a gap in dualtrack".
---

# Ask for a feature in Dualtrack

1. Ask what Dualtrack should do that it does not, and what they were trying to do when they noticed. One question, in their words.
2. Draft the request in two or three plain sentences: what they wanted, what happened, what would help. Keep out product names, repo names, code, numbers and people unless the user asks to include them; the request goes to someone outside their company.
3. Show the draft and ask if it is right. Change it until they say yes.
4. Run, from the folder that holds profile.md:

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/request.py" --share issue "<the approved draft>"
```

Use `--share email` if they prefer email or have no GitHub account. It opens their browser or mail app with the request filled in, plus the kit's version.

5. Tell them: nothing is sent until they press submit or send. Never submit it for them.
