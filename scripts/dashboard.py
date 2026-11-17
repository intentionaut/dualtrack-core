#!/usr/bin/env python3
"""The owner's dashboard: one page, built from the record the loop already keeps. No model call, sends nothing.

  dashboard.py <context> <date> [kit] [cap] [profile.md]   write <context>/dashboard.html

The words come from the profile (Product, Goal, Mode, Launched), so one page fits any kind of product.

Reading order is the order of what the owner must do: what needs them, whether shipped work helped, then cost.
Colour carries meaning only: teal is working or helped, violet needs the owner, grey is neutral or unknown.
"""
import datetime
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import loop_lib
import profile_value
import status

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = ("https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600&family=Inter:wght@400;500;600"
         "&family=JetBrains+Mono:wght@400;500&display=swap")
e = lambda s: html.escape(str(s), quote=True)


def read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return ""


def runs(context, date):
    """Each costed run as (days before date, outcome, dollars)."""
    today = datetime.date.fromisoformat(date)
    out = []
    for line in read(f"{context}/team-log.md").splitlines():
        c = [x.strip() for x in line.split("|")]
        m = re.match(r"^- (\d{4}-\d{2}-\d{2})$", c[0]) if c else None
        if m and len(c) >= 3 and re.fullmatch(r"\$[0-9.]+", c[-1]):
            try:
                out.append(((today - datetime.date.fromisoformat(m[1])).days, c[1], float(c[-1][1:])))
            except ValueError:  # a hand-edited date that is not a date: the brief names it, the chart leaves it out
                pass
    return out


def money(x):
    return f"${x:,.2f}"


def card(k, v, n=""):
    return f'<div class="card"><div class="k">{e(k)}</div><div class="v num">{e(v)}</div><div class="n">{n}</div></div>'


def undo_form(decide, title, label):
    return (f'<form class="act undo" data-kind="undo" data-cmd="{e(decide)}" data-title="{e(title)}">'
            f'<button class="linkbtn" type="submit">{e(label)}</button></form>')


STATE_WORDS = {"pass": "Finished", "failed": "Failed", "waiting_for_decision": "Waiting for you", "blocked": "Blocked", "safety_stop": "Safety stop"}


def last_run_strip(context):
    """The last run in one line: its gate state in words, what it said, and the step that fits. Empty before the first run."""
    _, outcome, row = loop_lib.last_run(context)
    if not row:
        return ""
    step = row["next"] if row["state"] != loop_lib.PASS else ""
    return (f'<section id="last-run" class="strip {e(row["state"])}"><span class="st">{e(STATE_WORDS[row["state"]])}</span>'
            f'<span class="what"><b>Last run:</b> {e(outcome[:160])}</span>{"<span class=n>" + e(step) + "</span>" if step else ""}</section>')


def needs_you(brief, late, decide, answered=False, picked="", live=False, last=None):
    """One card per call, with real controls. Live, a call is recorded; otherwise it copies its exact command.
    A brief already answered drops its cards; a pick no run has started yet shows with an Undo."""
    rows, table, items = brief.get("options", []), brief.get("table", ""), []
    if picked:
        items.append(f'<div class="act done"><p>You picked <em>{e(picked)}</em>. The next run builds it.</p>'
                     f'{undo_form(decide, picked, "Undo")}</div>')
    if rows and not answered:
        opts = "".join(
            f'<label class="opt"><input type="radio" name="o" value="{n}"><span class="opt-n">{n}</span><span class="opt-b">'
            f'<span class="opt-t">{e(r["change"])}</span><span class="opt-d">{e(r.get("reason", ""))}'
            f'{" · expected: " + e(r["expected"]) if r.get("expected") else ""}</span></span></label>'
            for n, r in enumerate(rows, 1))
        items.append(
            f'<form class="act" data-kind="pick" data-cmd="{e(decide)}" data-table="{e(table)}">'
            f'<div class="act-h"><h3>Pick the next change</h3><span class="act-why">The team waits until you choose</span></div>'
            f'<fieldset class="opts"><legend class="sr">Options</legend>{opts}</fieldset>'
            f'<div class="act-f"><button class="btn primary" type="submit" disabled>Build this</button>'
            f'<details class="more"><summary>Something else</summary><div class="more-b">'
            f'<label>None of these, because<input type="text" name="no" placeholder="not this quarter"></label>'
            f'<label>Do this instead<input type="text" name="try" placeholder="what you want built"></label>'
            f'<button class="btn" type="button" data-alt>Send</button></div></details></div></form>')
    if brief.get("question") and not answered:
        items.append(
            f'<form class="act" data-kind="answer" data-cmd="{e(decide)}"><div class="act-h"><h3>The team asked</h3></div>'
            f'<p class="act-ctx">{e(brief["question"])}</p>'
            f'<label class="ev">Your answer<input type="text" name="answer" required></label>'
            f'<div class="act-f"><button class="btn primary" type="submit">Answer</button></div></form>')
    # Allow only where the loop asked a real question about a bet; a safety stop has none, so it never gets a card.
    if last and last["offer"] == "allow" and brief.get("question") and brief.get("bet") and not answered:
        items.append(
            f'<form class="act" data-kind="allow" data-cmd="{e(decide)}"><div class="act-h"><h3>Let it through?</h3>'
            f'<span class="act-why">Dualtrack agents held <em>{e(brief["bet"])}</em> for you</span></div>'
            f'<div class="act-f"><button class="btn primary" type="submit">Let it through</button></div></form>')
    if last and last["offer"] == "resume":
        items.append(
            f'<form class="act" data-kind="resume" data-cmd="{e(decide)}"><div class="act-h"><h3>Carry on?</h3>'
            f'<span class="act-why">Two changes in a row were closed, so Dualtrack agents paused</span></div>'
            f'<div class="act-f"><button class="btn primary" type="submit">Carry on</button></div></form>')
    for o in late:
        items.append(
            f'<form class="act" data-kind="result" data-cmd="{e(decide)}" data-title="{e(o["title"])}">'
            f'<div class="act-h"><h3>Did <em>{e(o["title"])}</em> help?</h3>'
            f'<span class="act-why">Window ended on {e(o["read_by"])}</span></div>'
            f'<p class="act-ctx">Outcome: {e(o["expected"] or "not recorded")}. Main metric before: {e(o["baseline"] or "unknown")}. Guardrails: {e(o.get("guardrails") or "none named")}.</p>'
            f'<div class="seg" role="radiogroup" aria-label="Verdict">'
            f'<label><input type="radio" name="v" value="helped"><span>It helped</span></label>'
            f'<label><input type="radio" name="v" value="no"><span>It did not help</span></label>'
            f'<label><input type="radio" name="v" value="unclear"><span>Too early to tell</span></label></div>'
            f'<label class="ev">What you saw <span class="opt-d">(optional)</span><input type="text" name="ev"></label>'
            f'<div class="act-f"><button class="btn primary" type="submit" disabled>Save result</button></div></form>')
    if not items:
        return 0, ""
    asks = len(items) - bool(picked)
    how = ("Each button records your call at once." if live else
           'Each button copies the exact call; paste it into <code class="say">/dualtrack</code> or your terminal.')
    return asks, (f'<section id="needs-you" class="ask-s"><div class="sh"><h2>Needs you</h2>'
                        f'<span class="count" id="ask-count">{asks}</span></div>'
                        f'<p class="lede">Nothing moves until you answer. {how}</p>{"".join(items)}</section>')


VERDICT_WORDS = set(loop_lib.VERDICTS.values())
STATUS = {"Helped": "helped", "Did not help": "no", "Unclear": "wait", "Evidence in": "late", "Shipped, awaiting evidence": "wait"}


def did_it_help(outs, date, launched=True, goal="", decide=""):
    if not launched:
        return (f'<section id="outcomes"><div class="sh"><h2>Did it help?</h2><span class="count">not launched</span></div>'
                f'<p class="lede">No users yet, so there is nothing to measure. Results start after launch'
                f'{", against your goal: " + e(goal) if goal else ""}. Until then, this page leads with what the team delivered.</p></section>',
                "after launch")
    if not outs:
        return (f'<section id="outcomes"><div class="sh"><h2>Did it help?</h2><span class="count">none shipped</span></div>'
                f'<p class="lede">Nothing shipped yet. Each merged change will appear here and wait for evidence'
                f'{" against your goal: " + e(goal) if goal else ""}.</p></section>', "none yet")
    helped = sum(o["status"] == "Helped" for o in outs)
    judged = sum(o["status"] in ("Helped", "Did not help") for o in outs)
    rows = ""
    for o in sorted(outs, key=lambda o: list(STATUS).index(o["status"]) if o["status"] in STATUS else 9):
        late = o["status"] == "Shipped, awaiting evidence" and o["read_by"] and o["read_by"] <= date
        word, cls = ("Result due", "late") if late else (o["status"].replace("Shipped, awaiting evidence", "Waiting"), STATUS.get(o["status"], "wait"))
        now = o["evidence"] or (f"window ends {o['read_by']}" if o["read_by"] else "unknown")
        why = (f"Result recorded {o['day']}: {o['evidence']}" if o["evidence"] else "No result yet.") + \
              (f" Window ends {o['read_by']}." if o["read_by"] else "") + (f" Guardrails: {o.get('guardrails')}." if o.get("guardrails") else "") + (f" Stop rule: {o.get('stop')}." if o.get("stop") else "")
        rows += (f'<tr class="row" tabindex="0" aria-expanded="false"><td><span class="st {cls}">{e(word)}</span></td>'
                 f'<td class="t">{e(o["title"])}</td><td class="m">{e(o["expected"] or "not recorded")}</td>'
                 f'<td class="m">{e(o["baseline"] or "unknown")}</td><td class="m">{e(now)}</td></tr>'
                 f'<tr class="ev-row" hidden><td></td><td colspan="4">{e(why)}'
                 f'{undo_form(decide, o["title"], "Undo this verdict") if o["status"] in VERDICT_WORDS and decide else ""}</td></tr>')
    lede = ((f"Goal: {goal}. " if goal else "") + f"{len(outs)} shipped. Of those with your verdict, {helped} helped." if judged else
            (f"Goal: {goal}. " if goal else "") + f"{len(outs)} shipped, none judged yet. Merging is not the end: each waits for evidence.")
    return (f'<section id="outcomes"><div class="sh"><h2>Did it help?</h2><span class="count">{len(outs)} shipped</span></div>'
            f'<p class="lede">Select a row for the evidence. {e(lede)} A metric moving does not prove a change caused it.</p>'
            f'<table><tr><th style="width:130px">Status</th><th>Bet</th><th>Outcome</th><th>Before</th><th>Now</th></tr>{rows}</table></section>',
            f"{helped} of {judged}" if judged else "none judged")


def bets_board(cols, decide="decide"):
    """The bets board: a column per stage, a card per bet, each naming who signed it."""
    total = sum(map(len, cols.values()))
    if not total:
        return ""
    out = ""
    for name, cards in cols.items():
        out += f'<div class="col"><h3>{e(name)} <span class="count">{len(cards)}</span></h3>'
        for c in cards:
            agents = c["owner"] == loop_lib.AGENTS
            tags = "".join(f'<span class="tag{" area" if i == 0 else ""}">{e(t)}</span>' for i, t in ((0, c["area"]), (1, c["kind"])) if t)
            out += (f'<article class="bet">{"<div class=tags>" + tags + "</div>" if tags else ""}'
                    f'<h4>{e(c["title"])}</h4>{"<p>" + e(c["note"]) + "</p>" if c["note"] and c["note"] != c["status"] else ""}'
                    f'<p class="who">{e(c["status"])} · {e(c["day"])} · Owner <strong{" class=agents" if agents else ""}>{e(c["owner"])}</strong></p>'
                    f'<details><summary>Change owner</summary><form class="act owner" data-kind="owner" data-cmd="{e(decide)}" data-title="{e(c["title"])}">'
                    f'<label>New owner <input name="owner" maxlength="60" autocomplete="name"></label>'
                    f'<button type="submit" disabled>Save</button></form></details></article>')
        out += "</div>"
    return (f'<section id="bets"><div class="sh"><h2>Bets</h2><span class="count">{total}</span></div>'
            f'<p class="lede">Every bet, by stage. Each card names who signed it.</p><div class="board">{out}</div></section>')


def cost(rs, cap):
    week = [r for r in rs if 0 <= r[0] < 7]
    spent, before = sum(r[2] for r in week), sum(r[2] for r in rs if 7 <= r[0] < 14)
    weeks = [sum(r[2] for r in rs if 7 * i <= r[0] < 7 * (i + 1)) for i in (3, 2, 1, 0)]
    top = max(weeks) or 1
    bars = "".join(
        f'<rect x="{40 + 144 * i}" y="{124 - 90 * w / top:.0f}" width="96" height="{90 * w / top:.0f}" rx="2" class="bar{" now" if i == 3 else ""}">'
        f'<title>{"This week" if i == 3 else f"{3 - i} weeks ago" if i < 2 else "Last week"}: {money(w)}</title></rect>'
        f'<text x="{88 + 144 * i}" y="{116 - 90 * w / top:.0f}" text-anchor="middle">{money(w)}</text>'
        f'<text x="{88 + 144 * i}" y="142" text-anchor="middle">{"This week" if i == 3 else "Last week" if i == 2 else f"{3 - i} weeks ago"}</text>'
        for i, w in enumerate(weeks))
    stops = {}
    for _, outcome, _ in week:
        if loop_lib.gate_state(outcome) != loop_lib.PASS:
            stops[outcome[:90]] = stops.get(outcome[:90], 0) + 1
    biggest = max((r[2] for r in week), default=0)
    capped = re.sub(r"[^0-9.]", "", cap or "")
    cap_text = money(float(capped)) if capped.replace(".", "", 1).isdigit() else "none"
    stop_list = "".join(f'<li><span>{e(k)}</span><span class="m">{n}×</span></li>' for k, n in stops.items()) or "<li><span>None this week</span></li>"
    return (f'<section id="cost"><div class="sh"><h2>Cost and delivery</h2><span class="count">this week</span></div>'
            f'<p class="lede">{money(spent)} over {len(week)} runs; the week before, {money(before)}. Every call is in costs.md.</p>'
            f'<div class="cards">{card("Spent", money(spent), f"last week <b>{money(before)}</b>")}'
            f'{card("Runs", len(week), f"{len(stops)} not finished")}'
            f'{card("Largest run", money(biggest), "Run cap <b>" + e(cap_text) + "</b> · set in profile.md")}</div>'
            f'<div class="card" style="border:1px solid var(--hair);border-radius:var(--radius-lg)"><div class="k">Spend by week</div>'
            f'<svg viewBox="0 0 600 150" width="100%" role="img" aria-label="Spend by week, oldest first: {", ".join(money(w) for w in weeks)}">'
            f'<line x1="0" y1="124" x2="600" y2="124" stroke="var(--hair)"/>{bars}</svg></div>'
            f'<div class="sh" style="margin-top:20px"><h2 style="font-size:14px">Where runs stopped</h2></div><ul class="stops">{stop_list}</ul></section>',
            money(spent))


def render(context, date, kit="", cap="", profile="", live=""):
    text = read(profile) if profile else ""
    product = profile_value.field(text, "Product").split(",")[0].split(" - ")[0].strip()[:40]
    goal, mode = profile_value.field(text, "Goal"), profile_value.field(text, "Mode")
    launched = profile_value.field(text, "Launched").lower() not in ("no", "not yet", "false")
    try:
        brief = json.loads(read(f"{context}/options.json") or "{}")
    except ValueError:
        brief = {}
    decide = f"python3 {kit}/scripts/decide.py" if kit else "decide"
    picked = loop_lib.bet_title_clean(loop_lib.confirmed(read(f"{context}/bets.md")))
    day, _, last = loop_lib.last_run(context)
    if last and status.called_since(context, day):
        last = None  # the owner's call is in; the card would only repeat it
    asks, needs = needs_you(brief, loop_lib.overdue(context, date), decide, status.answered(context, brief), picked, bool(live), last)
    helped_html, helped = did_it_help(list(loop_lib.outcomes(context).values()), date, launched, goal, decide)
    cost_html, spent = cost(runs(context, date), cap)
    summary = (f'<nav class="summary" aria-label="Summary">'
               f'<a class="{"ask" if asks else ""}" href="#needs-you"><div class="k">Needs you</div><div class="v num">{asks}</div></a>'
               f'<a class="good" href="#outcomes"><div class="k">Bets that helped</div><div class="v num">{e(helped)}</div></a>'
               f'<a href="#outcomes"><div class="k">Waiting for evidence</div><div class="v num">'
               f'{sum(o["status"] == "Shipped, awaiting evidence" for o in loop_lib.outcomes(context).values())}</div></a>'
               f'<a href="#cost"><div class="k">Spent this week</div><div class="v num">{spent}</div></a></nav>')
    body = f"{last_run_strip(context)}\n{summary}\n{needs}\n{bets_board(loop_lib.board(context), decide)}\n" + (f"{helped_html}\n{cost_html}\n" if launched else f"{cost_html}\n{helped_html}\n")
    return (f'<!doctype html>\n<html lang="en-GB">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>Dualtrack dashboard</title>\n'
            f'{"<meta name=dualtrack-live content=" + chr(34) + e(live) + chr(34) + ">" if live else ""}\n'
            f'<link rel="preconnect" href="https://fonts.googleapis.com">\n<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
            f'<link href="{FONTS}" rel="stylesheet">\n<style>\n{read(os.path.join(HERE, "dashboard.css"))}</style>\n</head>\n<body>\n<main>\n'
            f'<header><div><p class="eyebrow">DUALTRACK{" · " + e(product.upper()) if product else ""}</p><h1>Your product operating system</h1>'
            f'{"<p class=fresh>Working on " + e(mode) + "</p>" if mode else ""}'
            f'<p class="fresh">Updated {e(date)}</p></div><button class="theme" type="button" id="theme">Dark mode</button></header>\n'
            f'{body}'
            f'<p class="foot">Built from your record: options.json, bets.md, decisions.md, team-log.md. Spend is estimated from Claude usage. '
            f'This page sends none of your data anywhere; it loads its fonts from Google Fonts.</p>\n</main>\n'
            f'<script>\n{read(os.path.join(HERE, "dashboard.js"))}</script>\n</body>\n</html>\n')


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip())
        return 2
    context, date = argv[0], argv[1]
    page = render(context, date, *argv[2:5])
    with open(f"{context}/dashboard.html", "w") as f:
        f.write(page)
    print(f"dashboard: {context}/dashboard.html")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
