#!/usr/bin/env python3
"""Answer the morning brief. Run from your repo: it finds profile.md there, or in a state repo beside it.

  decide.py 1 [table]          build option 1, signing its Done when lines; the brief gives the table's id, so a pick from an older brief is refused
  decide.py criteria 1 "line" ["line" ...]   build option 1 against your own Done when lines; again before its build starts to change them
  decide.py no "why"           none of today's options; Dualtrack agents will not offer them again
  decide.py done 1 "how"       option 1, or a bet by title, was settled without code
  decide.py try "what"         ask Dualtrack agents for something else; the next run takes it first
  decide.py answer "text"      answer Dualtrack's question
  decide.py allow ["title"]    let the bet Dualtrack agents held for you through, and build it again (refused after a safety stop)
  decide.py resume             let a paused team carry on
  decide.py result "title" helped|no|unclear ["evidence"]
                               what came of a shipped bet; merging it was not the end
  decide.py undo "title"       take back a pick no run has started, or your verdict on a shipped bet
  decide.py owner "title" "name"  sign off a bet, or hand it to someone else (unsigned bets are Dualtrack agents')
  decide.py note "text"        keep a note in the record; nothing is built
  decide.py notice off         hide the note that points to Team
  decide.py areas              take the team's proposed map of product areas, or mark yours looked at today
  decide.py areas no           keep your map; that proposal is not offered again
  decide.py --from-doc         read the owner's calls from the brief doc reader on stdin
"""
import datetime
import json
import os
import re
import profile_value  # noqa: E402
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import loop_lib


def repo_name():
    """The GitHub repo's name, from origin, so every clone finds the same record whatever its folder is called."""
    r = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True)
    m = re.search(r"[:/]([^/]+?)(?:\.git)?/?$", r.stdout.strip()) if r.returncode == 0 else None
    return m[1] if m else os.path.basename(os.getcwd())


def find_profile():
    """profile.md here, or this repo's folder in a state repo beside it (setup --state).
    Records filed before the repo name was used sit under the folder name, so that is tried second."""
    if os.path.exists("profile.md"):
        return "profile.md"
    # One listing of the folders beside this one (a file cannot hold a state repo), not one per name tried.
    try:
        beside = sorted(e.name for e in os.scandir("..") if e.is_dir())
    except OSError:
        beside = []
    for name in dict.fromkeys([repo_name(), os.path.basename(os.getcwd())]):
        for parent in beside:
            candidate = os.path.join("..", parent, name, "profile.md")
            if os.path.isfile(candidate) and "**State repo:**" in open(candidate).read():
                return candidate
    return "profile.md"


def context_path(profile=None):
    profile = profile or find_profile()
    try:
        value = profile_value.field(open(profile).read(), "Context path")
    except OSError:
        value = ""
    return value or "./product-context"


def record(context, line):
    with open(os.path.join(context, "decisions.md"), "a") as f:
        f.write(line + "\n")


def sign_row(context, row, lines, by, today):
    """Sign a picked row's Done when lines, or say why the team will write them unsigned."""
    if not lines:
        return "no Done when lines to sign: the team writes them, and the pull request says they are unsigned"
    bad = loop_lib.lint({"done_when": lines})
    if bad:
        return f"not signed: {'; '.join(bad)}. To sign your own, run: decide.py criteria N \"line\" ..."
    loop_lib.sign(context, row["change"], lines, by, today)
    return "signed the Done when lines:\n" + "".join(f"- {l}\n" for l in lines).rstrip()


def from_doc(text):
    """The doc reader's JSON as decide commands. Nothing when the owner has not answered."""
    # Only the reader's own answer, its last json block: a block or brace quoted from the doc earlier never counts.
    blocks = re.findall(r"```json\s*\n(.*?)\n```", text, re.S)
    try:
        calls = json.loads(blocks[-1]) if blocks else {}
    except ValueError:
        return None
    if not isinstance(calls, dict):
        return None
    if not calls.get("found"):
        return None
    reply = str(calls.get("reply") or "").strip()
    out = []
    build = calls.get("build")
    build = [build] if isinstance(build, int) else build if isinstance(build, list) else []
    if build:
        # Several picks queue as bets; the loop builds the oldest first, one a run.
        try:
            rows = len(json.load(open(os.path.join(context_path(), "options.json"))).get("options") or [])
        except (OSError, ValueError):
            rows = 0
        # A pick names a row of today's table; any other number is not the owner's call.
        out += [[str(n)] for n in build if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= rows]
    elif calls.get("not_now"):
        out.append(["no", reply or "not now, from the brief doc"])
        reply = ""
    if reply:
        try:
            asked = json.load(open(os.path.join(context_path(), "options.json"))).get("question")
        except (OSError, ValueError):
            asked = ""
        # A reply answers the open question. With no question, it is kept for the owner, never turned into a bet:
        # a model read it from the doc, and only the owner's own command confirms a bet.
        out.append(["answer" if asked else "note", reply])
    return out


FREE_TEAMS = 6  # product teams Dualtrack Free covers in one state repo; setup_apply.team_limit uses this too
TEAM_TEAMS = 12  # Team covers 7 to 12; 13 and over is Enterprise
PRICING_URL = "https://dualtrack.intentionaut.com/pricing/"
CONTACT_URL = "https://dualtrack.intentionaut.com/contact/"


def teams_filed(home):
    """Product teams in a state repo: folders holding a profile.md. The one count Free's limit and the notice share."""
    return sum(1 for d in os.scandir(home) if d.is_dir() and os.path.isfile(os.path.join(d.path, "profile.md"))) if os.path.isdir(home) else 0


def team_notice(context):
    """#241: one line pointing to Team at the 6 product teams Free covers, and to Enterprise at the 12 Team covers. Never blocks; `decide.py notice off` hides it.
    Counts folders on this machine; nothing is sent anywhere. Kept here, not in loop_lib, which is a pinned safety file."""
    try:
        state = re.search(r"^\*\*State repo:\*\* *(.+)$", open(find_profile()).read(), re.M)
    except OSError:
        return ""
    n = teams_filed(state[1].strip()) if state else 0
    if n < FREE_TEAMS or os.path.exists(os.path.join(context, "team-notice-off")):
        return ""
    if n < TEAM_TEAMS:
        have, then = "Free", f"needs the Team tier: {PRICING_URL}"
    else:
        have, then = "Team", f"needs Enterprise: talk to us at {CONTACT_URL}"
    return (f"note: this state repo holds {n} product teams, which is what Dualtrack {have} covers. "
            f"The next one {then}. To hide this: decide.py notice off")


def main(argv, today=None, save=True):
    if argv == ["--from-doc"]:
        commands = from_doc(sys.stdin.read())
        if commands is None:
            print("the brief doc could not be read")
            return 3
        for c in commands:
            main(c, today, save=False)  # the loop saves the state repo at the end of its run
        if not commands:
            print("no call in the brief doc yet")
            return 5
        return 0
    today = today or datetime.date.today().isoformat()
    # Who makes the call: --by "<name>" for a teammate, else the profile's Owner. A name only, on one line.
    by = ""
    if "--by" in argv:
        i = argv.index("--by")
        by, argv = (argv[i + 1] if i + 1 < len(argv) else ""), argv[:i] + argv[i + 2:]
    if not by:
        try:
            by = profile_value.field(open(find_profile()).read(), "Owner")
        except OSError:
            by = ""
    by = " ".join(by.replace("|", "/").split())[:60] if by and not by.startswith("<") else ""
    signed = f" | by: {by}" if by else ""  # decision provenance: every call names who made it
    if not argv or (argv[0] not in ("resume", "allow", "areas") and not loop_lib.pick(argv[0]) and len(argv) < 2) \
            or (argv[0] == "criteria" and (len(argv) < 3 or not loop_lib.pick(argv[1]))):
        print(__doc__.strip())
        return 2
    context = context_path()
    if not os.path.isdir(context):  # run from a folder that is not the product's: nothing is recorded, so nothing is said
        print(f"no record at {context}: run this from your product repo, where profile.md is")
        return 2
    try:
        brief = json.load(open(os.path.join(context, "options.json")))
    except OSError:
        brief = {"options": [], "question": ""}
    cmd, text = argv[0], " ".join(argv[1:]).strip().replace("|", "/")
    bets = os.path.join(context, "bets.md")
    if loop_lib.pick(cmd):
        rows = brief["options"]
        if not 1 <= int(cmd) <= len(rows):
            print(f"no option {cmd}: today's brief has {len(rows)}")
            return 4
        # The table id from the brief the owner read. Without one, the pick binds to the current table, as before.
        seen = argv[1] if len(argv) > 1 else ""
        if seen and seen != (brief.get("table") or loop_lib.table_id(rows)):
            print(f"today's brief changed since you read it: option {cmd} is now \"{rows[int(cmd) - 1]['change']}\". "
                  f"To build that, run: decide.py {cmd} {brief.get('table') or loop_lib.table_id(rows)}")
            return 4
        row = rows[int(cmd) - 1]
        kind = f"{row['type']}, {row['priority']}" if row.get("type") and row.get("priority") else ""
        print(loop_lib.confirm(bets, row["change"], today, kind, by, loop_lib.area_named(row.get("reason", ""), context)))
        print(sign_row(context, row, row.get("done_when") or [], by, today))
    elif cmd == "criteria":
        rows = brief["options"]
        if not 1 <= int(argv[1]) <= len(rows):
            print(f"no option {argv[1]}: today's brief has {len(rows)}")
            return 4
        lines = [" ".join(l.replace("|", "/").split()) for l in argv[2:] if l.strip()]
        bad = loop_lib.lint({"done_when": lines})
        if bad:  # the same rule the PM's lines meet: an outcome a test or the owner can see
            print("not signed: " + "; ".join(bad))
            return 4
        row = rows[int(argv[1]) - 1]
        kind = f"{row['type']}, {row['priority']}" if row.get("type") and row.get("priority") else ""
        print(loop_lib.confirm(bets, row["change"], today, kind, by, loop_lib.area_named(row.get("reason", ""), context)))
        print(sign_row(context, row, lines, by, today))
    elif cmd == "try":
        print(loop_lib.confirm(bets, text, today, by=by))
    elif cmd == "done":
        what, _, how = text.partition(" ")
        rows = brief["options"]
        title = rows[int(what) - 1]["change"] if loop_lib.pick(what) and 1 <= int(what) <= len(rows) else None
        if title is None:  # a title, quoted as the first argument
            title, how = argv[1].replace("|", "/"), " ".join(argv[2:]).replace("|", "/")
        if not how.strip():
            print('say how it was settled: decide.py done 1 "how"')
            return 2
        with open(bets, "a") as f:
            f.write(f"- {today} | {loop_lib.bet_title_clean(title)} | started: resolved: {how.strip()}{signed}\n")
        print(f"resolved without code: {title}")
    elif cmd == "no":
        for row in brief["options"]:
            record(context, f"- {today} | {row['change'].replace('|', '/')} | rejected by owner: {text}{signed}")
        print(f"recorded: none of {len(brief['options'])} options, because {text}")
    elif cmd == "answer":
        record(context, f"- {today} | owner answer to: {brief.get('question') or 'the open question'} | {text}{signed}")
        # A question Dualtrack agents asked about a bet: the answer goes to the engineer, and the bet builds again.
        if brief.get("bet"):
            with open(os.path.join(context, "answers.md"), "a") as f:
                f.write(f"- {today} | {loop_lib.bet_title_clean(brief['bet'])} | {text}\n")
            print(loop_lib.confirm(bets, brief["bet"], today, by=by))
        print("recorded your answer")
    elif cmd == "allow":
        # The owner lets one bet past the holds that ask them (never the safety stops), and it builds again.
        _, outcome, row = loop_lib.last_run(context)
        if row and row["state"] == loop_lib.SAFETY:
            print(f"Nothing to allow. The last run ended on a safety stop, not a question: {loop_lib.oneline(outcome)}\n"
                  "Allowing a bet would not lift it. Read the reason above, fix what it names, then run again.")
            return 4
        title = brief.get("bet") if text in ("", "yes") else text
        if not title:
            print('say which bet: decide.py allow "<title>"')
            return 2
        with open(os.path.join(context, "allowed.md"), "a") as f:
            f.write(f"- {today} | {loop_lib.bet_title_clean(title)} | allowed by owner{signed}\n")
        # A held change already built waits on its branch: the next run resumes it, so no bet is needed.
        if os.path.exists(os.path.join(context, "resume-branch.txt")):
            print(f"allowed: {title}; the next run picks up the built change")
        else:
            print(loop_lib.confirm(bets, title, today, by=by))
    elif cmd == "result":
        title, verdict, evidence = argv[1].replace("|", "/").strip(), (argv[2:3] or [""])[0].lower(), " ".join(argv[3:]).replace("|", "/").strip()
        if verdict not in loop_lib.VERDICTS:
            print('say helped, no or unclear: decide.py result "title" helped "evidence"')
            return 2
        if loop_lib.bet_title(title) not in loop_lib.outcomes(context):
            print(f"no shipped bet called \"{title}\"; the inbox lists them")
            return 4
        with open(bets, "a") as f:
            f.write(f"- {today} | {loop_lib.bet_title_clean(title)} | result: {verdict}: {evidence or 'no evidence given'}{signed}\n")
        print(f"recorded: {title}: {loop_lib.VERDICTS[verdict].lower()}")
    elif cmd == "owner":
        # Hand a bet to someone else. Append-only: the latest owner line wins.
        title, name = argv[1].replace("|", "/").strip(), " ".join(" ".join(argv[2:]).replace("|", "/").split())[:60]
        try:
            known = open(bets).read()
        except OSError:
            known = ""
        if not name or loop_lib.bet_title(title) not in loop_lib.owners(known):
            print('say a bet in the record, and a name: decide.py owner "title" "name"' if name else "say the new owner's name")
            return 4
        with open(bets, "a") as f:
            f.write(("" if not known or known.endswith("\n") else "\n") + f"- {today} | {loop_lib.bet_title_clean(title)} | owner: {name}{signed}\n")
        print(f"owner of {loop_lib.bet_title_clean(title)}: {name}")
    elif cmd == "undo":
        code, msg = loop_lib.undo(bets, argv[1].replace("|", "/"), today, by)
        print(msg)
        if code:
            return code
    elif cmd == "note":
        record(context, f"- {today} | brief doc reply, not acted on | {text}")
        print(f'kept your reply from the brief doc. To ask for it, run: decide.py try "{text}"')
    elif cmd == "areas":
        print(loop_lib.accept_areas(context, today, take=text.lower() not in ("no", "keep")))
    elif cmd == "notice" and text == "off":
        open(os.path.join(context, "team-notice-off"), "a").close()
        print("hid the Team notice for this record")
    elif cmd == "resume":
        record(context, f"- {today} | owner | resume{signed}")
        print("Dualtrack agents will carry on at the next run")
    else:
        print(__doc__.strip())
        return 2
    loop_lib.main(["inbox", context, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))])
    note = team_notice(context)
    if note:
        print(note)
    return 0 if not save or save_state(context) else 1


def net(cmd, default=60):
    """Run a command that talks to the network: it never waits on a password prompt, and it is cut off with everything
    it started after NET_TIMEOUT seconds (`default` when unset). Same shape as subprocess.run(text=True, capture_output=True); a cut-off has returncode 124."""
    import signal
    timeout = int(os.environ.get("NET_TIMEOUT") or default)
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}, start_new_session=True)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        p.communicate()
        return subprocess.CompletedProcess(cmd, 124, "", f"timed out after {timeout}s")
    return subprocess.CompletedProcess(cmd, p.returncode, out, err)


def save_state(context):
    """With a state repo, a cloud run reads the call from GitHub, so it has to get there. False when it did not."""
    m = re.search(r"^\*\*State repo:\*\* *(.+)$", open(find_profile()).read(), re.M)
    if not m:
        return True
    state = m[1].strip()
    git = lambda *a: subprocess.run(["git", "-C", state, *a], capture_output=True, text=True)
    # Only this product's folder, so another product's unsaved files in the same checkout never ride along.
    mine = os.path.relpath(os.path.realpath(context), os.path.realpath(state))
    git("add", "-A", "--", mine)
    if git("diff", "--cached", "--quiet", "--", mine).returncode:
        who = git("config", "user.name").stdout.strip() or "owner"
        c = git("commit", "-qm", f"{os.path.basename(os.path.dirname(os.path.abspath(context)))}: {who}'s call", "--", mine)
        if c.returncode:
            print(f"not saved: git could not commit in {state}: {(c.stderr.strip().splitlines() or ['no reason given'])[-1]}. Your call is in the files; fix that, then run this again.")
            return False
    if not git("remote").stdout.strip():  # Dualtrack state on this machine only: the commit is the save
        print("saved on this machine")
        return True
    # Pulled once, pushed once: another machine's push is carried under this call; a conflict is left for the owner.
    gitnet = lambda *a: net(["git", "-C", state, *a])
    pushed = gitnet("pull", "-q", "--rebase", "--autostash").returncode == 0 and gitnet("push", "-q").returncode == 0
    if not pushed:
        git("rebase", "--abort")
    print("saved for the next run" if pushed else f"not pushed: run git -C {state} pull --rebase && git -C {state} push (on a conflict, fix the files it names first), or the next cloud run will not see this")
    return pushed


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
