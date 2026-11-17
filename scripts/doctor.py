#!/usr/bin/env python3
"""Local health and friction report for one Dualtrack profile.

  doctor.py <profile> [--since YYYY-MM-DD] [--report]

Health: the tamper check, the sandbox, the state repo and the plugin version, each ok or a problem with its fix.
Friction since a date (default 7 days): what the run events in <context>/events/ record. A count the events do not
record is printed "unknown", never 0. Read-only. The one network call is `git ls-remote` on your own state repo.
--report prints the same as a fenced block you can paste to the maintainer. Nothing is sent.

Free tier stays local; hosted tiers may send it later (not built).
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

KIT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KIT, "scripts"))
import profile_value  # noqa: E402
import tamper  # noqa: E402

CAP = re.compile(r"over the \$\S+ cap")
SANDBOX = re.compile(r"sandbox", re.I)


def home(value):
    """The same rule as daily_loop.sh: a relative path is under the owner's dir, else the repo, else here."""
    if not value or os.path.isabs(value):
        return value
    top = os.environ.get("DUALTRACK_OWNER_DIR") or subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip() or os.getcwd()
    return os.path.normpath(os.path.join(top, value))


def field(text, name):
    v = profile_value.field(text, name)
    return "" if v.startswith("<") else v


def sandbox_problem():
    """(problem, fix) when branch code has no sandbox on this machine, else (None, ""). setup_check.py uses it too."""
    if shutil.which("sandbox-exec"):
        return None, ""
    if shutil.which("bwrap") and subprocess.run(["bwrap", "--ro-bind", "/", "/", "--unshare-net", "true"],
                                                capture_output=True).returncode == 0:
        return None, ""
    return ("no sandbox available for branch code",
            "macOS has sandbox-exec built in; on Linux install bubblewrap, and on Ubuntu 24.04 also run "
            "`echo 'kernel.apparmor_restrict_unprivileged_userns=0' | sudo tee /etc/sysctl.d/60-dualtrack-bwrap.conf && sudo sysctl --system`. That setting applies to the whole machine, not only Dualtrack, and the one-off form (sudo sysctl -w) is lost on reboot.")


def health(text):
    out = []
    bad = tamper.changed(KIT)
    out.append(("tamper check", None if not bad else tamper.message(bad).split(". Put the file", 1)[0],
                "put the file back with `git checkout -- <file>`, or install Dualtrack again" if bad else ""))
    sb = sandbox_problem()
    out.append(("sandbox available", sb[0], sb[1]))
    out.append(("state repo reachable", *state_repo(home(field(text, "State repo")))))
    try:
        with open(os.path.join(KIT, ".claude-plugin", "plugin.json")) as f:
            out.append(("plugin version " + json.load(f)["version"], None, ""))
    except (OSError, ValueError, KeyError):
        out.append(("plugin version", "plugin.json is unreadable", "install Dualtrack again"))
    return out


def state_repo(path):
    if not path:
        return None, ""  # none set: the record stays on this machine
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        if not subprocess.run(["git", "-C", path, "remote"], capture_output=True, text=True, timeout=15).stdout.strip():
            return None, ""  # local only, nothing to reach
        r = subprocess.run(["git", "-C", path, "ls-remote", "--exit-code", "origin", "HEAD"],
                           capture_output=True, text=True, timeout=15, env=env)
    except (OSError, subprocess.TimeoutExpired):
        return "the state repo did not answer in 15 seconds", f"check the network, then run `git -C {path} ls-remote origin`"
    return (None, "") if r.returncode == 0 else (
        "the state repo remote could not be read", f"run `git -C {path} ls-remote origin` and fix the login or the URL")


def events(ctx, since):
    """The run events on or after `since`, or None when there is no events folder."""
    d = os.path.join(ctx, "events")
    if not os.path.isdir(d):
        return None
    out = []
    for n in sorted(os.listdir(d)):
        try:
            with open(os.path.join(d, n)) as f:
                ev = json.load(f)
            if datetime.date.fromisoformat(ev["time"][:10]) >= since:
                out.append(ev)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return out


def friction(evs, since):
    """Each count, or the string "unknown" when the events cannot say."""
    if not evs:
        why = "unknown (no run events since %s)" % since
        return {k: why for k in ("held changes", "owner questions", "sandbox stops", "run-cap overruns")} | \
            {"preflight stops": "unknown", "tamper stops": "unknown"}
    kind = lambda e: str(e.get("kind", ""))
    return {
        "runs": str(len(evs)),
        "held changes": str(sum(kind(e).startswith("held") for e in evs)),
        "owner questions": str(sum(bool(e["question"]) for e in evs)) if all("question" in e for e in evs) else "unknown",
        "preflight stops": "unknown",  # a preflight run writes no event
        "sandbox stops": str(sum(kind(e).startswith("stopped") and bool(SANDBOX.search(str(e.get("outcome", "")))) for e in evs)),
        "tamper stops": "unknown",  # the tamper stop comes before a run has anywhere to write an event
        "run-cap overruns": str(sum(bool(CAP.search(str(e.get("outcome", "")))) for e in evs)),
    }


def render(profile, since, report):
    with open(profile) as f:
        text = f.read()
    lines = ["Health"]
    for name, problem, fix in health(text):
        lines.append(f"  ok       {name}" if not problem else f"  PROBLEM  {name}: {problem}\n           fix: {fix}")
    lines += ["", f"Friction since {since}"]
    ctx = home(field(text, "Context path") or "./product-context")
    evs = events(ctx, since)
    if evs is None:
        lines.append("  unknown (no events folder yet; it fills after the first run)")
    else:
        lines += [f"  {k}: {v}" for k, v in friction(evs, since).items()]
    body = "\n".join(lines)
    return f"```\nDualtrack doctor\n{body}\n```" if report else body


def main(argv):
    since = datetime.date.today() - datetime.timedelta(days=7)
    args = [a for a in argv if a != "--report"]
    if "--since" in args:
        i = args.index("--since")
        try:
            since = datetime.date.fromisoformat(args[i + 1])
        except (IndexError, ValueError):
            print("--since needs a date like 2026-11-08")
            return 2
        del args[i:i + 2]
    if len(args) != 1 or not os.path.isfile(args[0]):
        print(__doc__.strip())
        return 2
    print(render(args[0], since, "--report" in argv))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
