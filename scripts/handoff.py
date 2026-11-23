#!/usr/bin/env python3
"""Dualtrack's interface for other agents and workflows.

    handoff.py context <profile>                   the context pack: goal, bets, open change, options, decisions, conventions
    handoff.py event <profile> <outcome> [--send]  the run's event; writes <context>/events/<time>.json, and with --send
                                                   posts it to DUALTRACK_WEBHOOK_URL, signed with DUALTRACK_WEBHOOK_SECRET

Both print schema-versioned JSON (dualtrack.context.v1, dualtrack.run.v1). Other agents steer Dualtrack agents back
through decide.py: try "what", answer "text", allow, done N "how", no "why".

A post is never sent if it holds DUALTRACK_CANARY (the run's fake token), and a failed send never stops a run.
"""
import datetime
import hashlib
import hmac
import json
import os
import re
import socket
import profile_value  # noqa: E402
import sys
import urllib.error
import urllib.parse
import urllib.request

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KIT, "scripts"))
import loop_lib


def field(profile_text, name):
    value = profile_value.field(profile_text, name)
    return "" if value.startswith("<") else value


def read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return ""


def context_dir(profile):
    path = field(read(profile), "Context path") or "./product-context"
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(os.getcwd(), path))


def tail_lines(text, n):
    return [l for l in text.splitlines() if l.startswith("- ")][-n:]


def context(profile):
    text, ctx = read(profile), context_dir(profile)
    brief = json.loads(read(os.path.join(ctx, "options.json")) or "{}")
    log = tail_lines(read(os.path.join(ctx, "team-log.md")), 1)
    return {
        "schema": "dualtrack.context.v1",
        "product": field(text, "Product"),
        "audience": field(text, "Audience"),
        "goal": field(text, "Goal"),
        "mode": field(text, "Mode"),
        "confirmed_bet": loop_lib.confirmed(read(os.path.join(ctx, "bets.md"))) or None,
        "last_run": log[0][2:] if log else None,
        "options": brief.get("options", []),
        "question": brief.get("question") or None,
        "recent_decisions": tail_lines(read(os.path.join(ctx, "decisions.md")), 10),
        "conventions": tail_lines(read(os.path.join(ctx, "conventions.md")), 20),
        "lessons": tail_lines(read(os.path.join(ctx, "lessons.md")), 20),
        "product_memory": "product.md",
        "product_areas": "areas.md",
        "steer": {"build option": "decide.py N", "ask for something": 'decide.py try "what"',
                  "answer the question": 'decide.py answer "text"', "let a held change through": "decide.py allow",
                  "settled without code": 'decide.py done N "how"', "none of these": 'decide.py no "why"'},
    }


def event(profile, outcome, now=None):
    ctx = context(profile)
    week = read(os.path.join(context_dir(profile), "weekly.md"))
    today = (now or datetime.datetime.now()).date().isoformat()
    url = re.search(r"https://\S+/pull/\d+", outcome)
    return {
        "schema": "dualtrack.run.v1",
        "time": (now or datetime.datetime.now(datetime.timezone.utc)).isoformat(timespec="seconds"),
        "product": ctx["product"],
        "goal": ctx["goal"],
        "outcome": outcome,
        "kind": outcome.split(":", 1)[0].strip(),
        "gate_state": loop_lib.gate_state(outcome),  # pass, failed, waiting_for_decision, blocked or safety_stop: the one word to route on
        "pull_request": url[0].rstrip(",") if url else None,
        "options": ctx["options"],
        "question": ctx["question"],
        "confirmed_bet": ctx["confirmed_bet"],
        "steer": ctx["steer"],
        "weekly": week if week.startswith(f"## This week, to {today}") else None,
        "safety_checks": [l[2:] for l in read(os.environ.get("DUALTRACK_CHECKS", "")).splitlines() if l.startswith("- ")],
    }


def sign(body, secret):
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """A webhook that answers with a redirect is not followed: the signature and event stay with the host set."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def send(ev, env=os.environ):
    url = env.get("DUALTRACK_WEBHOOK_URL")
    if not url:
        return "no webhook set"
    body = json.dumps(ev).encode()
    canary = env.get("DUALTRACK_CANARY")
    if canary and canary.encode() in body:
        return "not delivered: the event holds the run's canary token"
    # scan unescaped: json.dumps escapes a zero-width space, so leaks() could not strip it
    found = loop_lib.leaks(json.dumps(ev, ensure_ascii=False))  # test or setup output can reach the outcome line before the record's own scan
    if found:
        return f"not delivered: the event holds {found[0]}"
    # The host itself, not the start of the URL: http://127.0.0.1.example.com is someone else's machine.
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" and not (parts.scheme == "http" and parts.hostname == "127.0.0.1"):
        return "not delivered: the webhook must be https"
    headers = {"Content-Type": "application/json", "User-Agent": "dualtrack"}
    if env.get("DUALTRACK_WEBHOOK_SECRET"):
        headers["X-Dualtrack-Signature"] = sign(body, env["DUALTRACK_WEBHOOK_SECRET"])
    try:
        with urllib.request.build_opener(NoRedirect).open(urllib.request.Request(url, data=body, headers=headers, method="POST"), timeout=20) as r:
            return f"sent: {r.status}"
    # The run's work is saved either way; a failed send is reported in the brief, never fatal, and never sent again by itself.
    except urllib.error.HTTPError as e:
        return f"not delivered: the receiver answered HTTP {e.code}"
    except urllib.error.URLError as e:  # nothing answered: refused or unresolvable means it never arrived; anything else may have
        refused = isinstance(e.reason, (ConnectionRefusedError, socket.gaierror))
        return f"{'not delivered' if refused else 'delivery unknown'}: {e.reason}"
    except Exception as e:  # a timeout, or a reply that never came: the receiver may hold the event
        return f"delivery unknown: {e}"


def main(a):
    if a[:1] == ["context"] and len(a) == 2:
        print(json.dumps(context(a[1]), indent=2))
        return 0
    if a[:1] == ["event"] and len(a) >= 3:
        ev = event(a[1], a[2])
        out = os.path.join(context_dir(a[1]), "events")
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, ev["time"].replace(":", "") + ".json"), "w") as f:
            json.dump(ev, f, indent=2)
        if "--send" in a:
            print(send(ev))
        return 0
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
