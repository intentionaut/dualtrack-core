#!/usr/bin/env python3
"""File the setup agent's draft and the owner's answers, the same way every time.

Usage, from the root of the product repo, when Dualtrack's state repo already holds this product's record
(setup_check.py says "Already set up"): python3 <kit>/scripts/setup_apply.py --join
It clones the state repo beside this one, or updates it, and asks nothing: the record is Dualtrack's, not this machine's.

Otherwise, after the setup agent wrote setup.md:
  python3 <kit>/scripts/setup_apply.py --record state|local --runs cloud|local --ponytail yes|no
      --code-review yes|no --auto-merge yes|no --design yes|no [--run-cap <dollars>|none] [--tests "<command>"] [--test-network on --allowed-domains "<domains>"] [--create-state]

--record state keeps the record in <owner>/dualtrack-state, cloned beside this repo (--create-state makes it,
private, when the owner agreed). --record local keeps it in this repo, listed in .git/info/exclude.
Prints what it did, and the profile path on the last line. Never changes the product repo's tracked files.
"""
import datetime
import json
import os
import pathlib
import re
import subprocess
import sys

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
import decide  # noqa: E402
import file_setup  # noqa: E402
import profile_value  # noqa: E402
import setup_check  # noqa: E402
GH = os.environ.get("GH_BIN", "gh")
RUN_CAP = "10"  # the suggested limit a run, in dollars, until the owner picks their own
FREE_TEAMS = decide.FREE_TEAMS
TEAM_WAITLIST = json.loads((KIT / "feedback.json").read_text())["team_waitlist_url"]  # contact links live in feedback.json
LOCAL_FILES = ["profile.md", "setup-notes.md", "numbers.md", "product-context/"]


def run(*cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"stopped: `{' '.join(cmd)}` failed: {(r.stderr or r.stdout).strip()[-300:]}")
    return r.stdout.strip()


def ponytail():
    """"ponytail <newest installed version>": the loop runs only the version the profile names, so an update is reviewed."""
    cache = pathlib.Path(os.environ.get("CLAUDE_CONFIG_DIR") or pathlib.Path.home() / ".claude", "plugins/cache/ponytail/ponytail")
    found = [d.name for d in cache.glob("*") if (d / "skills/ponytail/SKILL.md").is_file()]
    key = lambda v: [int(x) if x.isdigit() else -1 for x in re.split(r"[.+-]", v)]
    return f"ponytail {max(found, key=key)}" if found else "ponytail"


DEFAULTS = {"ponytail": "yes", "code-review": "no", "auto-merge": "no", "design": "no"}
# What each default sets in the profile, and the value that turns it the other way.
LATER = {"ponytail": ("Engineer rules", "none"), "code-review": ("Code review", "on"),
         "auto-merge": ("Auto-merge", "on, with Code review on"), "design": ("Design rules", "frontend-design"),
         "test-network": ("Test network", "on, with Allowed domains")}


def same_identity(home):
    """The product repo's git name and email, set in Dualtrack state too: a per-folder identity would not reach it, and every save commits there."""
    for key in ("user.name", "user.email"):
        if not subprocess.run(["git", "-C", str(home), "config", key], capture_output=True).stdout.strip():
            value = subprocess.run(["git", "config", key], capture_output=True, text=True).stdout.strip()
            run("git", "-C", str(home), "config", key, value or ("Dualtrack" if key == "user.name" else "dualtrack@localhost"))


def opt(argv, name, choices, default=None):
    if name not in argv and default is not None:
        return default
    value = argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None
    if value not in choices:
        raise SystemExit(f"stopped: {name} must be one of {', '.join(choices)}")
    return value


def state_name(argv):
    """Always dualtrack-state: one record per GitHub owner, so every team in an organisation is counted together."""
    if "--state-repo" in argv:
        raise SystemExit("stopped: the state repo name is fixed at dualtrack-state, so every team shares one record. Nothing was changed.")
    return "dualtrack-state"


def set_line(profile, name, value):
    line = f"**{name}:** {value}"
    pattern = rf"^\*\*{re.escape(name)}:\*\*.*$"
    return re.sub(pattern, lambda _: line, profile, flags=re.M) if re.search(pattern, profile, re.M) else profile.rstrip() + f"\n\n{line}\n"


def join(name, create=False, share_all=False):
    """A teammate or a second machine: use the record Dualtrack already has, never a second one."""
    m = re.search(r"github\.com[:/]([^/]+)/", run("git", "remote", "get-url", "origin"))
    state_repo, home = f"{m[1] if m else ''}/{name}", pathlib.Path("..") / name
    if home.exists() and m and not run("git", "-C", str(home), "remote"):
        # Set up before GitHub: this Dualtrack state goes to GitHub whole, so its history comes too.
        if not subprocess.run([GH, "repo", "view", state_repo, "--json", "name"], capture_output=True).returncode:
            raise SystemExit(f"stopped: {state_repo} already exists on GitHub. Nothing was changed. Ask its owner for access, then run setup_apply.py --join.")
        if not create:
            raise SystemExit(f"stopped: {state_repo} does not exist yet. Ask the owner, then run again with --create-state.")
        # The whole history goes, so every product filed here goes too: only with the owner's say-so.
        others = sorted(d.name for d in home.iterdir() if (d / "profile.md").exists()
                        and d.name not in (decide.repo_name(), os.path.basename(os.getcwd())))
        if others and not share_all:
            raise SystemExit(f"stopped: {home} also holds {', '.join(others)}, so they would go to {state_repo} too. "
                             "Nothing was changed. To put them all on GitHub, run again with --share-all.")
        run(GH, "repo", "create", state_repo, "--private")
        run("git", "-C", str(home), "remote", "add", "origin", run(GH, "repo", "view", state_repo, "--json", "url", "-q", ".url"))
        run("git", "-C", str(home), "push", "-q", "-u", "origin", "HEAD")
        print(f"- put Dualtrack state on GitHub: {state_repo}, private, with its history")
    elif home.exists():
        run("git", "-C", str(home), "pull", "-q")
        print(f"- updated {home} from {state_repo}")
    else:
        run(GH, "repo", "clone", state_repo, str(home))
        print(f"- cloned {state_repo} to {home}")
    # Under the repo's name, or under the folder's when it was filed before GitHub, as decide.find_profile() reads it.
    profile_path = next((home / f / "profile.md" for f in (decide.repo_name(), os.path.basename(os.getcwd()))
                         if (home / f / "profile.md").exists()), home / decide.repo_name() / "profile.md")
    if not profile_path.exists():
        raise SystemExit(f"stopped: {state_repo} has no {decide.repo_name()}/profile.md; run setup without --join")
    print(f"- joined: this checkout uses Dualtrack's record, so its calls and runs land in the same place")
    print(str(profile_path))
    return 0


def team_limit(home, profile_path):
    """Free covers 6 product teams in one state repo. A 7th new product stops here; the 6 already filed are untouched."""
    if profile_path.exists():
        return
    filed = decide.teams_filed(home)
    if filed >= FREE_TEAMS:
        raise SystemExit(f"stopped: {home} already holds {filed} products, and Dualtrack Free covers {FREE_TEAMS}. "
                         f"Nothing was changed, and those {filed} keep running as before. "
                         "Dualtrack Team is for more than 6 and is not open yet: join the waitlist at "
                         f"{TEAM_WAITLIST} and you will hear first when it opens.")


def main(argv):
    if "--join" in argv:
        return join(state_name(argv), "--create-state" in argv, "--share-all" in argv)
    name = state_name(argv)
    origin = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True)
    m = re.search(r"github\.com[:/]([^/]+)/", origin.stdout) if origin.returncode == 0 else None
    owner = m[1] if m else None
    # Setup asks three questions; everything else takes the recommended answer, listed at the end.
    record = opt(argv, "--record", ("state", "local"), "state")
    runs = opt(argv, "--runs", ("cloud", "local"), "cloud" if owner and record == "state" else "local")
    answers = {k: opt(argv, f"--{k}", ("yes", "no"), DEFAULTS[k]) for k in DEFAULTS}
    defaulted = [k for k in DEFAULTS if f"--{k}" not in argv] + ([] if "--test-network" in argv else ["test-network"])
    tests = argv[argv.index("--tests") + 1] if "--tests" in argv else ""
    test_network = opt(argv, "--test-network", ("on", "off")) if "--test-network" in argv else "off"
    domains = ", ".join(d.strip() for d in argv[argv.index("--allowed-domains") + 1].split(",") if d.strip()) \
        if "--allowed-domains" in argv else ""
    if test_network == "on" and not domains:
        raise SystemExit("stopped: Test network on needs --allowed-domains, so the engineer's own test runs reach them too")
    focus = " ".join(argv[argv.index("--focus") + 1].split()) if "--focus" in argv else ""
    # The bets' owner: their answer, else their git name. A name, never a pipe or a new line in the record.
    owner_name = (argv[argv.index("--owner") + 1] if "--owner" in argv else
                  subprocess.run(["git", "config", "user.name"], capture_output=True, text=True).stdout).strip()
    owner_name = re.sub(r"[|\n\r]", " ", owner_name)[:60].strip()
    # The most one run may spend, in dollars: their answer, else the suggested default. "none" turns the limit off.
    run_cap = (argv[argv.index("--run-cap") + 1] if "--run-cap" in argv and argv.index("--run-cap") + 1 < len(argv) else RUN_CAP).strip().lstrip("$")
    if run_cap.lower() not in ("none", "off", "no") and not re.fullmatch(r"\d{1,4}(\.\d{1,2})?", run_cap) or run_cap in ("0", "0.0", "0.00"):
        raise SystemExit("stopped: --run-cap must be a dollar amount, such as 10, or none")
    if runs == "cloud" and record == "local":
        raise SystemExit("stopped: cloud runs need the record in a state repo; choose --record state or --runs local")
    if answers["auto-merge"] == "yes" and answers["code-review"] == "no":
        raise SystemExit("stopped: auto-merge needs Code Review on")
    if not os.path.exists("setup.md"):
        raise SystemExit("stopped: setup.md is missing; run the setup agent first")
    if runs == "cloud" and not owner:
        raise SystemExit("stopped: cloud runs need a GitHub repo. Nothing was changed. Use --runs local, or add one with `gh repo create`.")
    # The command that will be filed: the owner's --tests, else the one setup.md names. A command that cannot run stops every later run.
    command = tests or profile_value.field(file_setup.runnable_tests(open("setup.md").read()), "Test commands")
    if command:
        code, out = setup_check.sh(command)  # shortcut: no box, so a test that needs the network or keys is not refused for lacking them
        if code != 0:
            last = [l for l in out.strip().splitlines() if l.strip()][-1:]
            raise SystemExit(f"stopped: the test command `{command}` does not run here: {' '.join(last)}. Nothing was changed. "
                             "Run again with --tests \"<a command that runs>\", for example one that starts with python3.")
    file_args = [sys.executable, str(KIT / "scripts/file_setup.py"), "setup.md"]
    if record == "state" and not owner:
        # No GitHub yet: Dualtrack state is its own git repo beside this one, so it keeps its history until it is pushed.
        home = pathlib.Path("..") / name
        if not home.exists():
            run("git", "init", "-q", str(home))
            print(f"- made Dualtrack state in {home}")
        elif os.path.realpath(subprocess.run(["git", "-C", str(home), "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip() or "/") != os.path.realpath(home):
            raise SystemExit(f"stopped: {home} exists and is not a git repo. Nothing was changed. Move it.")
        elif subprocess.run(["git", "-C", str(home), "remote"], capture_output=True, text=True).stdout.strip():
            # It is another product's GitHub state: filing here would push this record to that repo.
            raise SystemExit(f"stopped: {home} is on GitHub, and this product is not. Nothing was changed. "
                             "Add a GitHub repo for this product with `gh repo create`, then run setup again.")
        same_identity(home)
        file_args += ["--state", str(home)]
        profile_path = home / decide.repo_name() / "profile.md"
    elif record == "state":
        state_repo, home = f"{owner}/{name}", pathlib.Path("..") / name
        if subprocess.run([GH, "repo", "view", state_repo, "--json", "name"], capture_output=True).returncode:
            if "--create-state" not in argv:
                raise SystemExit(f"stopped: {state_repo} does not exist; ask the owner, then run again with --create-state")
            run(GH, "repo", "create", state_repo, "--private")
            print(f"- created {state_repo}, private. A state repo holds Dualtrack's own record (notes, numbers, decisions), apart from your code")
        if not home.exists():
            run(GH, "repo", "clone", state_repo, str(home))
            print(f"- cloned {state_repo} to {home}")
        same_identity(home)
        file_args += ["--state", str(home)]
        profile_path = home / decide.repo_name() / "profile.md"
    else:
        profile_path = pathlib.Path("profile.md")
    if record == "state":
        team_limit(home, profile_path)
    print(run(*file_args))
    profile = profile_path.read_text()
    for name, value in (("Brief doc", "none" if runs == "cloud" else "claude"),
                        ("Engineer rules", ponytail() if answers["ponytail"] == "yes" else "none"),
                        ("Code review", "on" if answers["code-review"] == "yes" else "off"),
                        ("Auto-merge", "on" if answers["auto-merge"] == "yes" else "off"),
                        ("Design rules", "frontend-design" if answers["design"] == "yes" else "none"),
                        ("Test network", test_network),
                        ("Run cap", "none" if run_cap.lower() in ("none", "off", "no") else run_cap)):
        profile = set_line(profile, name, value)
    if tests:
        profile = set_line(profile, "Test commands", tests)
    # Only the owner's answer sets this: a draft written from a repo's text never widens the network.
    profile = set_line(profile, "Allowed domains", domains or "none")
    if focus:
        profile = set_line(profile, "Focus", focus)
    if owner_name:
        profile = set_line(profile, "Owner", owner_name)
    profile_path.write_text(profile)
    # The setup call's cost goes in the record with every later call's, so the owner sees what setup cost.
    if os.path.exists("setup.json"):
        try:
            cost = json.load(open("setup.json")).get("total_cost_usd")
        except ValueError:
            cost = None
        ctx = re.search(r"^\*\*Context path:\*\* *(.+)$", profile, re.M)
        if ctx:
            ctx_dir = pathlib.Path(ctx[1].strip())
            ctx_dir.mkdir(parents=True, exist_ok=True)
            with open(ctx_dir / "costs.md", "a") as f:
                f.write(f"- {datetime.date.today().isoformat()} | setup | setup draft | default model | ${cost if cost is not None else 'unknown'}\n")
        os.remove("setup.json")
    print("- set Brief doc, Engineer rules, Code review, Auto-merge, Design rules, Allowed domains and Run cap from the answers")
    print("  Run cap is the most one run may spend. Auto-merge, when on, lets a small change that passes every check merge on its own; it is off by default.")
    if not domains:
        print("- Allowed domains is none; add domains to profile.md later if the tests need them")
    if record == "local":
        exclude = pathlib.Path(run("git", "rev-parse", "--git-common-dir")) / "info" / "exclude"
        exclude.parent.mkdir(parents=True, exist_ok=True)
        have = exclude.read_text().splitlines() if exclude.exists() else []
        with exclude.open("a") as f:
            f.write("".join(f"{p}\n" for p in LOCAL_FILES if p not in have))
        print(f"- kept the record out of git: {', '.join(LOCAL_FILES)} are in {exclude}")
    else:
        home = profile_path.parent.parent
        run("git", "-C", str(home), "add", "-A", "--", profile_path.parent.name)
        if subprocess.run(["git", "-C", str(home), "diff", "--cached", "--quiet"]).returncode:
            run("git", "-C", str(home), "commit", "-qm", f"{profile_path.parent.name}: setup")
        if not owner:
            print("- saved the record on this machine")
        else:
            pushed = subprocess.run(["git", "-C", str(home), "push", "-q"], capture_output=True).returncode == 0
            print(f"- {'pushed' if pushed else 'NOT pushed, run git -C ' + str(home) + ' push'} the record to {owner}/{name}")
    if defaulted:
        print(f"Set for you. Change any of these later in {profile_path}:")
        for k in defaulted:
            line, other = LATER[k]
            current = re.search(rf'^\*\*{line}:\*\* *(.*)$', profile, re.M)[1]  # not inside the f-string: a backslash there is a SyntaxError before Python 3.12
            print(f"- {line}: {current}. To change it, set **{line}:** to {other}.")
    os.remove("setup.md")  # last, so a failed save can be run again without a second setup call
    print(str(profile_path))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
