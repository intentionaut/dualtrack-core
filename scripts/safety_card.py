#!/usr/bin/env python3
"""Locked areas and the safety card, in plain words. All copy here is draft.

Usage:
  safety_card.py suggest                       from the product repo: the setup card, areas found in its files
  safety_card.py locked <profile> <diff.txt> <title> [oneline]
                                               exit 4 and the stop message when the change touches a locked area
  safety_card.py revert <profile> <diff.txt> <base>
                                               put every locked file the change touched back as on base, and commit
  safety_card.py stop <area> <title>           the same message, for an engineer that stopped before editing
  safety_card.py stop-question <area> <title>  the same stop on one line, for the owner question in the brief
  safety_card.py card <run> <profile> <repo> <base> <branch> <context> [failed]
                                               the safety card for a finished bet (run holds item.json, engineer.txt)

A locked area is a `**Locked area:** <plain name> :: <path regex>` line in the profile. A card row is Passed, Stopped
or Not checked. A check the run rewrote can never be Passed: the loop reads that from the branch, not from the report.
"""
import os
import re
import subprocess
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import profile_value  # noqa: E402

# shortcut: areas are found by words in file paths, not by reading the code. Upgrade when a missed area is reported.
AREAS = {
    "Payments and checkout": r"checkout|payment|billing|invoice|(^|/)cart",
    "Login and accounts": r"login|sign-?in|(^|/)auth|account|password",
    "Emails to customers": r"e-?mail|newsletter",
    "Pricing page": r"pricing",
}
TEST = r"(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]*$|[._]test\.[^/]*$|[._]spec\.[^/]*$|_test\.[^/]*$"
LOCKED = re.compile(r"^\*\*Locked area:\*\* *(.+?) :: (.+?) *$", re.M)
W = 52
CHOICES = ("Allow a change to {a}, just for this bet", "Find a version that leaves {a} alone", "Drop this bet")


def is_test(path):
    return bool(re.search(TEST, path))


def suggest(files):
    """[(plain name, path regex, matching files)] for each area the repo's files show. Tests are not the area."""
    out = []
    for name, rx in AREAS.items():
        hit = [f for f in files if not is_test(f) and re.search(rx, f, re.I)]
        if hit:
            out.append((name, rx, hit))
    return out


def setup_card(found):
    lines = ["⚙ Setup · What should never change without asking?", "",
             " Dualtrack won't touch these. If a bet needs one,", " it stops and asks you first.", ""]
    lines += [f" ⛒ {name}" for name, _, _ in found]
    lines += [" ☐ Anything else (describe it)", "", "   ↳ We found these in your code. You can change them any time.", "",
              " ❯ Looks right", "   Change the list"]
    return "\n".join(lines)


def save(profile, picks):
    """The profile with exactly these locked areas: [(name, regex)]. Every other line stays as it was."""
    kept = LOCKED.sub("", profile).rstrip("\n") + "\n"
    kept = re.sub(r"\n{3,}", "\n\n", kept)
    return kept + ("\n" + "".join(f"**Locked area:** {n} :: {rx}\n" for n, rx in picks) if picks else "")


def locked(profile):
    return [(n.strip(), rx.strip()) for n, rx in LOCKED.findall(profile)]


def touched(profile, paths, skip=()):
    """(area, path) for the first non-test file in a locked area, or None. A pattern that cannot be read locks everything.
    `skip` names areas the owner allowed for this bet; every other area stays locked."""
    skip = {a.lower() for a in skip}
    for name, rx in locked(profile):
        if name.lower() in skip:
            continue
        for p in paths:
            try:
                if not is_test(p) and re.search(rx, p, re.I):
                    return name, p
            except re.error:
                return name, p
    return None


def stop_message(area, title):
    a = area.lower()
    return "\n".join([f"⛨ Safety check · {title}", "", f" ✕ Stopped: this change needs {a}",
                      f"   ↳ {area} is on your locked list, so we stopped.",
                      "   ↳ Your product is unchanged. Nothing was shipped.", "", " What should happen?",
                      f" ❯ {CHOICES[0].format(a=a)}", f"   {CHOICES[1].format(a=a)}", f"   {CHOICES[2]}"])


def allowed_areas(allowed_path, bet):
    """The locked areas the owner allowed for this bet: `- <date> | <bet> | <area>` lines that `decide allow` writes
    to locked-allowed.md. An allow opens only the area it names, never the rest."""
    import loop_lib
    try:
        rows = [[x.strip() for x in l.split("|")] for l in open(allowed_path) if l.startswith("- ")]
    except OSError:
        return set()
    return {r[2] for r in rows if len(r) >= 3 and loop_lib.bet_title(r[1]) == loop_lib.bet_title(bet)}


def env_allowed():
    """The allowed areas for the bet a Dualtrack run names in its environment, as the hook and the loop's checks read them."""
    return allowed_areas(os.environ.get("DUALTRACK_LOCK_ALLOWED", ""), os.environ.get("DUALTRACK_LOCK_BET", ""))


def revert(profile, names, base, skip=()):
    """Put every locked file the change touched back as it is on `base`, and commit that. The backstop for a write the guard missed.
    Files in an area the owner allowed for this bet (`skip`) stay as built."""
    hits = [p for p in names if touched(profile, [p], skip)]
    for p in hits:
        if subprocess.run(["git", "cat-file", "-e", f"{base}:{p}"], capture_output=True).returncode == 0:
            subprocess.run(["git", "checkout", base, "--", p], check=True)
        else:
            subprocess.run(["git", "rm", "-qf", "--ignore-unmatch", "--", p], check=True)
    if hits:
        subprocess.run(["git", "commit", "-qm", "Put locked files back as they were", "--allow-empty"], check=True)
    return hits


def stop_question(area, title):
    """The same stop as one line: the brief shows an owner question on one line, so the three choices are numbered."""
    a = area.lower()
    return (f"Stopped \"{title}\": this change needs {a}, which is on your locked list. Your product is unchanged and nothing was shipped. "
            f"What should happen? 1) {CHOICES[0].format(a=a)}. 2) {CHOICES[1].format(a=a)}. 3) {CHOICES[2]}.")


def mode(profile):
    """Autonomy: with Auto-merge on, and not under Company mode, the card records; otherwise it asks."""
    on = lambda name: profile_value.field(profile, name).lower().split(" ")[:1] == ["on"]
    return "record" if on("Auto-merge") and not on("Company mode") else "ask"


def side_by_side(old, new, width=24):
    if not (old or new):
        return ["   What changed was not described."]
    a, b = textwrap.wrap(old or "not described", width) or [""], textwrap.wrap(new or "not described", width) or [""]
    rows = [("Was", "Now")] + [(x, y) for x, y in zip(a + [""] * (len(b) - len(a)), b + [""] * (len(a) - len(b)))]
    return [f"   {x:<{width + 2}}{y}".rstrip() for x, y in rows]


WHOSE = {"dualtrack": "Our change caused this.", "product": "This was already in your product, not our change.",
         "outside": "Something outside your product caused this."}
NONE = ("", "none", "none named", "unknown", "n/a")


def norm(path):
    """`./tests/x.py` and `tests/x.py::test_a` both name tests/x.py."""
    return re.sub(r"^(\./)+", "", path.split("::")[0].strip())


def render(c, rewritten=None):
    """The card as text. `rewritten` maps each test file the run rewrote to (old, new). A check that names one is never
    Passed, and a rewritten file no check names still gets its own Not checked row."""
    rewritten = {norm(k): v for k, v in (rewritten or {}).items()}
    claimed = {norm(t) for k in c["checks"] for t in k.get("tests", [])}
    rows, stopped, pending = [], False, bool(set(rewritten) - claimed)
    for k in c["checks"]:
        name, why = k["name"], k.get("why", "")
        grey = [f"   \u21b3 {why}"] if why else []
        rew = any(norm(t) in rewritten for t in k.get("tests", []))
        if k["result"] == "failed" and k.get("cause") != "out of date":
            stopped = True
            rows += [f" \u2715 Stopped: {name}"] + grey + [f"   What happened: {k.get('reason') or 'it did not say'}",
                     f"   {WHOSE.get(k.get('fault'), 'We could not tell whose fault this is.')}", "   We could not fix it ourselves.",
                     "   Your product is unchanged. Nothing was shipped."]
        elif k["result"] == "failed" or rew:
            pending = True
            rows += [f" \u2013 Not checked: {name}"] + grey + ["   This check was out of date, so it was rewritten in this run.",
                     "   A rewritten check cannot say Passed."] + side_by_side(k.get("was"), k.get("now"))
        elif c.get("tests_failed"):
            rows += [f" \u2013 Not checked: {name}"] + grey + ["   The checks did not all pass, so this was not counted."]
        else:
            if k.get("fixed"):
                rows += [f" \u2726 Fixed for you: {k.get('reason') or name}", "   \u21b3 Our change broke it. We put it back and checked again."]
            rows += [f" \u2713 {name}"] + grey
    if c.get("tests_failed"):
        stopped = True
        rows += [" \u2715 Stopped: the checks did not all pass", "   \u21b3 Every change has to leave the existing checks passing.",
                 "   Your product is unchanged. Nothing was shipped."]
    if set(rewritten) - claimed:
        n = len(set(rewritten) - claimed)
        rows += [f" \u2013 Not checked: {n} other check{' was' if n == 1 else 's were'} rewritten in this run",
                 "   \u21b3 No safety check above names it, so it was not counted."]
    # Each guardrail and the stop rule is a check: one nobody wrote is said out loud, not dropped.
    # shortcut: a guardrail counts as checked when a check's name holds its words, or the reverse; the engineer is told to reuse them.
    named = " ".join(k["name"].lower() for k in c["checks"])
    for text, what in [(g.strip(), "one of your guardrails") for g in c.get("guardrails", "").split(";")] + [(c.get("stop", "").strip(), "your stop rule")]:
        if text.lower() in NONE or text.startswith("<"):
            continue
        if text.lower() not in named and not any(k["name"].lower() in text.lower() for k in c["checks"]):
            rows += [f" \u2013 Not checked: {text}", f"   \u21b3 This is {what}. No check reads it yet."]
    rows += [f" \u2013 Not checked: {s}" for s in c.get("skipped", [])]
    aim = f" It should {c['outcome']}." if c.get("outcome") else ""
    if stopped:
        close = [" What should happen?", " \u276f Try again with a fix", "   Find another version", "   Drop this bet"]
    elif pending:
        close = [f" Approve the new check, then ship it?{aim}" if c.get("mode") != "record" else f" Recorded. The new check waits for your approval.{aim}"]
    else:
        close = [f" Ship it?{aim}" if c.get("mode") != "record" else f" Recorded, not asked. Your settings decide what happens next.{aim}"]
    return "\n".join([f"\u26e8 Safety check \u00b7 {c['title']}", "\u2500" * W] + rows + ["", *close])


def parse_report(text):
    """The engineer's `Checks:` lines and `Skipped:`/`Unchecked:` lines. Checks look like
    `- <name> | <why> | <test file> | passed` or `| failed: <out of date|product>: <reason> [| fault: dualtrack] [| was: .. | now: ..]`."""
    checks, skipped = [], []
    block = re.search(r"^Checks:[ \t]*\n((?:[ \t]*- .*\n?)+)", text, re.M)
    for line in (block[1].splitlines() if block else []):
        p = [x.strip() for x in line.strip()[2:].split(" | ")]
        if len(p) < 4:
            continue
        k = {"name": p[0], "why": p[1], "tests": [p[2]], "result": "passed"}
        m = re.match(r"failed(?:: (out of date|product)(?:: (.*))?)?$", p[3])
        if m:
            k.update(result="failed", cause=m[1] or "product", reason=m[2] or "")
        for extra in p[4:]:
            key, _, val = extra.partition(": ")
            if key in ("was", "now", "fault"):
                k[key] = val
            elif key == "fixed" and val.lower() != "no":
                k.update(fixed=True, reason=val)
        checks.append(k)
    for key in ("Skipped", "Unchecked"):
        m = re.search(rf"^{key}: *(.*)$", text, re.M)
        skipped += [s.strip() for s in (m[1] if m else "").split(";") if s.strip() and s.strip().lower() not in ("none", "nothing")]
    return {"checks": checks, "skipped": skipped}


def rewrites(repo, base, branch):
    """{test file: (old lines, new lines)} for each existing test file this branch changed by removing or replacing lines.
    A new test file, or a test only added to an old one, is not a rewrite."""
    def git(*a):
        return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True).stdout
    out = {}
    for row in git("diff", "--name-status", "--no-renames", base, branch).splitlines():
        status, _, path = row.partition("\t")
        if status not in ("M", "D") or not is_test(path):
            continue
        lines = [l for l in git("diff", "-U0", "--no-renames", base, branch, "--", path).splitlines() if l[:1] in "+-" and l[:3] not in ("+++", "---")]
        old = [l[1:] for l in lines if l[0] == "-"]
        if old:
            out[path] = ("\n".join(old).strip(), "\n".join(l[1:] for l in lines if l[0] == "+").strip())
    return out


def rewrote(names, numstat):
    """The existing test files a change rewrote, from `git diff --name-status` and `--numstat` rows: modified or deleted,
    with lines removed. The merge gate reads this, so a rewritten check always waits for the owner."""
    removed = {}
    for row in numstat:
        added, deleted, *path = row.split("\t")
        if deleted.isdigit() and int(deleted):
            removed[path[-1]] = True
    out = []
    for row in names:
        status, _, path = row.strip().partition("\t")
        if status in ("M", "D") and is_test(path) and removed.get(path):
            out.append(path)
    return out


def from_run(run, profile, repo, base, branch, context, tests_passed=True):
    import loop_lib
    import json
    item = json.load(open(os.path.join(run, "item.json")))
    try:
        report = parse_report(open(os.path.join(run, "engineer.txt")).read())
    except OSError:
        report = {"checks": [], "skipped": []}
    plan = {}
    try:
        for line in open(os.path.join(context, "bets.md")):
            cells = [x.strip() for x in line.split("|")]
            if line.startswith("- ") and len(cells) >= 3 and loop_lib.bet_title(cells[1]) == loop_lib.bet_title(item["title"]) and cells[2].startswith("expected:"):
                plan = loop_lib.plan_fields(cells)
    except OSError:
        pass
    card = {"title": item["title"], "outcome": f"help: {plan['expected']}" if plan.get("expected") else "", "mode": mode(profile),
            "guardrails": plan.get("guardrails", ""), "stop": plan.get("stop", ""), "tests_failed": not tests_passed, **report}
    return render(card, rewrites(repo, base, branch))


def main(argv):
    cmd, args = (argv or [""])[0], argv[1:]
    if cmd == "suggest":
        files = subprocess.run(["git", "ls-files"], capture_output=True, text=True).stdout.splitlines()
        print(setup_card(suggest(files)))
    elif cmd == "locked":
        names = [l.split("\t")[-1] for l in open(args[1]).read().splitlines() if l]
        hit = touched(open(args[0]).read(), names, env_allowed())
        if hit:
            print(stop_question(hit[0], args[2]) if args[3:4] == ["oneline"] else stop_message(hit[0], args[2]))
            return 4
    elif cmd == "revert":
        names = [l.split("\t")[-1] for l in open(args[1]).read().splitlines() if l]
        print("\n".join(revert(open(args[0]).read(), names, args[2], env_allowed())))
    elif cmd == "locked-area":
        names = [l.split("\t")[-1] for l in open(args[1]).read().splitlines() if l]
        hit = touched(open(args[0]).read(), names, env_allowed())
        print(hit[0] if hit else "")
    elif cmd == "allowed-areas":
        print(", ".join(sorted(allowed_areas(args[0], args[1]))))
    elif cmd == "stop-question":
        print(stop_question(args[0], args[1]))
    elif cmd == "stop":
        print(stop_message(args[0], args[1]))
    elif cmd == "card":
        print(from_run(args[0], open(args[1]).read(), *args[2:6], tests_passed=args[6:7] != ["failed"]))
    else:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
