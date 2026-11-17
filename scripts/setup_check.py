#!/usr/bin/env python3
"""Every check setup makes, in code, so each person gets the same checks and the same words.

Usage: python3 <kit>/scripts/setup_check.py [--tests "<command>"]     from the root of the product repo

Prints one line per check, then the facts setup asks from (owner, visibility, state repo, web pages, the test
command), as JSON on the last line. Exits 0 when every check passes, and 1 at the first that fails, with its fix.
It reads and runs the tests only: it never changes the repo.
"""
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import doctor  # noqa: E402  (its sandbox check is the one setup uses)

GH = os.environ.get("GH_BIN", "gh")


# Dualtrack agents run the tests with no outside network (daily_loop.sh's untrusted()), so setup checks them the same way.
# Name lookups go through the resolver's Unix socket and the ssh agent is one too: both closed, as in the loop. localhost TCP stays.
OFFLINE = ('(version 1)(allow default)(deny network-outbound (remote ip "*:*"))(allow network-outbound (remote ip "localhost:*"))'
           '(deny network-outbound (literal "/private/var/run/mDNSResponder"))(deny network-outbound (remote unix-socket))')


def watch_proxy():
    """A recording proxy that allows every host, so setup can name the domains the tests call. Returns (port, log, stop)."""
    import tempfile, time
    d = tempfile.mkdtemp()
    port_file, log = os.path.join(d, "port"), os.path.join(d, "egress.log")
    p = subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "egress_proxy.py"),
                          "--learn", port_file, log, "*"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        if os.path.exists(port_file) and open(port_file).read():
            break
        time.sleep(0.1)
    return open(port_file).read(), log, p.terminate


def dashboard_closed():
    """The dashboard's launch-secret folder (dashboard_server.py), closed to branch code run as the same user."""
    home = os.environ.get("DUALTRACK_HOME") or os.path.join(os.path.expanduser("~"), ".dualtrack")
    d = os.path.join(home, "dashboard"); os.makedirs(d, mode=0o700, exist_ok=True)
    return f'(deny file-read* file-write* (subpath "{os.path.realpath(d)}"))'


def scrubbed_net(cmd, port=""):
    """The tests as the loop runs them with Test network on: internet, no keys, home folder closed but the checkout.
    A test that passes only with the owner's own environment needs keys, and keys stay in CI."""
    import tempfile
    home, here = os.path.realpath(os.path.expanduser("~")), os.path.realpath(os.getcwd())
    tmp = os.path.realpath(tempfile.mkdtemp())
    env = scrubbed_env(tmp, port)
    dirs = [f"{home}/{d}" for d in (".pyenv", ".nvm", ".volta", ".cargo", ".rustup", ".bun", ".deno",
                                    ".rbenv", ".asdf", ".sdkman", "go", ".local/lib", ".local/bin")]
    git = os.path.realpath(subprocess.run(["git", "rev-parse", "--git-common-dir"], capture_output=True, text=True).stdout.strip() or ".")
    if not shutil.which("sandbox-exec"):
        box = []
        # Already inside a Dualtrack sandbox (the kit testing itself): the outer box still holds.
        if shutil.which("bwrap") and os.environ.get("DUALTRACK_SANDBOXED") != "1":
            # shortcut: the network stays whole here, so with a proxy port code that skips the proxy still gets out
            # (macOS closes that). Upgrade to the loop's socket proxy if setup must hold that line on Linux too.
            resolv = os.path.realpath("/etc/resolv.conf")  # Ubuntu's is a link into /run, which is emptied below
            dash = os.path.realpath(os.environ.get("DUALTRACK_HOME") or f"{home}/.dualtrack")
            box = ["bwrap", "--die-with-parent", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
                   *(["--tmpfs", "/run"] if os.path.isdir("/run") and not os.path.islink("/run") else []),
                   *(["--ro-bind", resolv, resolv] if resolv.startswith("/run/") and os.path.isfile(resolv) else []),
                   "--tmpfs", "/tmp", "--tmpfs", home, *(["--tmpfs", dash] if os.path.isdir(dash) else []),
                   *[a for d in dirs if os.path.isdir(d) for a in ("--ro-bind", d, d)],
                   # last, so they come back when they sit inside a folder emptied above
                   "--bind", git, git, "--bind", here, here, "--bind", tmp, tmp]
        return ["env", "-i", *[f"{k}={v}" for k, v in env.items()], *box, "bash", "-c", cmd]
    tools = "".join(f'(subpath "{d}")' for d in dirs)
    net = OFFLINE[len("(version 1)(allow default)"):] if port else ""
    box = (f'(version 1)(allow default){net}(deny file-read* file-write* (subpath "{home}"))'
           f'(allow file-read* file-write* (subpath "{here}") (subpath "{git}") (subpath "{tmp}"))(allow file-read* {tools})'
           f'{dashboard_closed()}(allow file-read-metadata)')
    return ["env", "-i", *[f"{k}={v}" for k, v in env.items()], "sandbox-exec", "-p", box, "bash", "-c", cmd]


def scrubbed_env(tmp, port=""):
    """What a test run may see: PATH, a throwaway HOME, locale. No keys, no owner settings."""
    env = {"PATH": os.environ.get("PATH", ""), "HOME": tmp, "TMPDIR": tmp, "LANG": os.environ.get("LANG", "C.UTF-8"),
           "TERM": "dumb", "PYTHONDONTWRITEBYTECODE": "1", "GIT_CONFIG_NOSYSTEM": "1", "DUALTRACK_SANDBOXED": "1"}
    if port:  # as the loop runs them: every request through the proxy, nothing else leaves the machine
        px = f"http://127.0.0.1:{port}"
        env.update({k: px for k in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy", "ALL_PROXY", "all_proxy",
                                    "GLOBAL_AGENT_HTTP_PROXY")}, NO_PROXY="localhost,127.0.0.1", no_proxy="localhost,127.0.0.1",
                   NODE_USE_ENV_PROXY="1")
    return env


def sh(cmd, timeout=600, offline=False, net=False, port=""):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")  # running the tests leaves no files behind
    if offline:
        # The owner's tests get no keys and a throwaway home, never this shell's environment.
        import tempfile
        tmp = os.path.realpath(tempfile.mkdtemp())
        env = scrubbed_env(tmp)
        # Already inside a Dualtrack sandbox (the kit testing itself): macOS cannot nest one, and the outer box still holds.
        if os.environ.get("DUALTRACK_SANDBOXED") != "1":
            if shutil.which("sandbox-exec"):
                cmd = ["sandbox-exec", "-p", OFFLINE + dashboard_closed(), "bash", "-c", cmd]
            elif shutil.which("bwrap"):  # shortcut: only the checkout and the throwaway home are writable; a test that commits in a linked worktree's main repo fails here
                here = os.path.realpath(os.getcwd())
                cmd = ["bwrap", "--die-with-parent", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
                       *(["--tmpfs", "/run"] if os.path.isdir("/run") and not os.path.islink("/run") else []),  # no ssh agent or other daemon sockets, as in the loop
                       "--tmpfs", "/tmp",  # a hand-started ssh-agent keeps its socket in /tmp; the checkout and throwaway home are bound back after it
                       "--bind", here, here, "--bind", tmp, tmp, "--unshare-net", "bash", "-c", cmd]
    elif net:
        cmd = scrubbed_net(cmd, port)
    try:
        r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, timeout=timeout, env=env)
        return r.returncode, r.stdout + r.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def test_command():
    """The repo's own test command, from the files that name one, in a fixed order."""
    try:
        script = json.load(open("package.json")).get("scripts", {}).get("test", "")
        if script and "no test specified" not in script:
            return "npm test"
    except (OSError, ValueError):
        pass
    if os.path.exists("Makefile") and re.search(r"^test:", open("Makefile").read(), re.M):
        return "make test"
    py = [os.path.join(d, f) for d, _, fs in os.walk(".") if "/." not in d and "node_modules" not in d
          for f in fs if re.match(r"(test_.*|.*_test)\.py$", f)]
    if py:
        if shutil.which("pytest") or sh([sys.executable, "-m", "pytest", "--version"])[0] == 0:
            return f"{sys.executable.rsplit('/', 1)[-1]} -m pytest -q"
        start = "tests" if os.path.isdir("tests") else "."
        # `-t .` makes tests/ a package, and discover refuses a tests/ folder with no __init__.py ("Start directory is not importable").
        if start == "tests" and not os.path.exists("tests/__init__.py"):
            return "python3 -m unittest discover tests"
        return f"python3 -m unittest discover -s {start} -t ."
    return ""


def tests_ran(output):
    """How many tests the runner says it ran, or None when it does not say."""
    for pattern in (r"^Ran (\d+) tests?", r"(\d+) passed", r"^ℹ tests (\d+)", r"^# tests (\d+)", r"Tests:\s+(\d+) passed"):
        m = re.search(pattern, output, re.M)
        if m:
            return int(m[1])
    return None


VENDORED = {"venv", "env", "vendor", "third_party", "node_modules"}  # shortcut: names only, not read from .gitignore


def unittest_misses(command):
    """Plain test_ functions that unittest never runs: a red test can hide behind a green run."""
    if "unittest" not in command:
        return []
    found = []
    # The user's own files only: tracked or new, not gitignored, and not code that lives in a vendored folder.
    listed = sh(["git", "ls-files", "-co", "--exclude-standard", "-z"])[1].split("\0")
    for path in listed:
        parts = path.split("/")
        if re.match(r"test_.*\.py$", parts[-1]) and not VENDORED.intersection(parts[:-1]) and os.path.isfile(path):
            found += [f"{path}:{n}" for n, line in enumerate(open(path, errors="replace"), 1) if re.match(r"def test_", line)]
    return found


def owner_of(remote):
    m = re.search(r"github\.com[:/]([^/]+)/([^/\s]+?)(?:\.git)?/?$", remote.strip())
    return (m[1], m[2]) if m else (None, None)


def web_pages():
    if any(os.path.exists(p) for p in ("index.html", "public/index.html", "src/pages", "app", "pages")):
        return True
    try:
        deps = json.load(open("package.json"))
        names = {**deps.get("dependencies", {}), **deps.get("devDependencies", {})}
        return any(n in names for n in ("astro", "next", "react", "vue", "svelte", "@sveltejs/kit", "nuxt", "vite"))
    except (OSError, ValueError):
        return False


def main(argv):
    given = argv[argv.index("--tests") + 1] if "--tests" in argv else ""
    facts = {}

    def fail(name, why, fix):
        print(f"- {name}: no. {why}\n\nStopped here. To fix it: {fix}\nThen run setup again. Nothing was changed.")
        print(json.dumps(dict(facts, ok=False, failed=name)))
        return 1

    def ok(name, detail=""):
        print(f"- {name}: yes{'. ' + detail if detail else ''}")

    if sh(["git", "rev-parse", "--git-dir"])[0] != 0:
        return fail("A git repo", "This folder is not a git repo.",
                    "run `git init` here, or run setup from your product's repo.")
    if os.environ.get("DUALTRACK_SANDBOXED") != "1":  # inside the loop's own box there is nothing to look for
        problem, fix = doctor.sandbox_problem()
        if problem:  # before any agent call, so nothing is spent on a setup that cannot finish
            return fail("A sandbox for branch code", f"There is {problem}.", fix + ".")
    code, remote = sh(["git", "remote", "get-url", "origin"])
    owner, repo = owner_of(remote) if code == 0 else (None, None)
    if "--state-repo" in argv:
        return fail("Dualtrack state name", "The state repo name is fixed at dualtrack-state, so every team shares one record.", "run the check again without --state-repo.")
    state_name = "dualtrack-state"
    # No GitHub yet: Dualtrack state is a git repo beside this one, on this machine, and GitHub waits until it is needed.
    facts["local_only"] = not owner
    if not owner:
        repo = os.path.basename(os.getcwd())  # as decide.repo_name() names it without a remote
        facts.update(owner=None, repo=repo, visibility="UNKNOWN", state_repo=f"../{state_name}", state_repo_exists=False,
                     state_repo_holds=[], set_up=os.path.exists(os.path.join("..", state_name, repo, "profile.md")))
        print("- A GitHub repo: not yet. Dualtrack state stays on this machine until you add one.")
        if facts["set_up"]:
            ok("Already set up", f"../{state_name} holds {repo}/profile.md.")
            print(json.dumps(dict(facts, ok=True)))
            return 0
    else:
        facts.update(owner=owner, repo=repo)
        ok("A GitHub repo", f"{owner}/{repo}")
    if owner and sh([GH, "auth", "status"])[0] != 0:
        return fail("GitHub sign-in", "`gh` is not signed in.", "type `! gh auth login` and follow the prompts.")
    if owner:
        ok("GitHub sign-in")
        # Set up before there was a GitHub repo: that Dualtrack state is the record, so setup never starts again.
        local = os.path.join("..", state_name)
        top = sh(["git", "-C", local, "rev-parse", "--show-toplevel"])[1].strip() if os.path.isdir(local) else ""
        held = [f for f in dict.fromkeys([repo, os.path.basename(os.getcwd())]) if os.path.isfile(os.path.join(local, f, "profile.md"))]
        if top and os.path.realpath(top) == os.path.realpath(local) and not sh(["git", "-C", local, "remote"])[1].strip() and held:
            facts.update(state_repo=f"{owner}/{state_name}", local_state=True, set_up=True)
            ok("Already set up", f"../{state_name} holds {held[0]}/profile.md, on this machine. To put it on GitHub: setup_apply.py --join")
            print(json.dumps(dict(facts, ok=True)))
            return 0
        vis = sh([GH, "repo", "view", f"{owner}/{repo}", "--json", "visibility", "-q", ".visibility"])[1].strip()
        facts["visibility"] = vis or "UNKNOWN"
        facts["state_repo"] = f"{owner}/{state_name}"
        facts["state_repo_exists"] = sh([GH, "repo", "view", facts["state_repo"], "--json", "name"])[0] == 0
        # Dualtrack was set up on this product already, from another machine or person: join that record, ask nothing.
        facts["set_up"] = facts["state_repo_exists"] and sh([GH, "api", f"repos/{facts['state_repo']}/contents/{repo}/profile.md",
                                                              "--silent"])[0] == 0
        # Other products already filed in this Dualtrack state: said before setup writes anything beside them.
        facts["state_repo_holds"] = [] if not facts["state_repo_exists"] else [
            d for d in sh([GH, "api", f"repos/{facts['state_repo']}/contents", "--jq", '.[] | select(.type == "dir") | .name'])[1].split()
            if d != repo and not d.startswith(".")]
        if facts["state_repo_holds"] and not facts["set_up"]:
            print(f"- Dualtrack state: {facts['state_repo']} already holds {', '.join(facts['state_repo_holds'])}. "
                  f"Setup adds {repo} beside them and changes nothing of theirs.")
        if facts["set_up"]:
            ok("Already set up", f"{facts['state_repo']} holds {repo}/profile.md. Join it: setup_apply.py --join")
            print(json.dumps(dict(facts, ok=True)))
            return 0
    facts["web"] = web_pages()
    facts["git_name"] = sh(["git", "config", "user.name"])[1].strip()[:60]  # suggested as the bets' owner
    facts["api_key"] = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if facts["api_key"]:
        print("- Claude plan, not an API key: ask. ANTHROPIC_API_KEY is set, so Dualtrack agents would bill that key, not the Claude plan.")
    else:
        ok("Claude plan, not an API key")
    command = given or test_command()
    if not command:
        return fail("Tests", "This repo has no test command setup can find.",
                    "add at least one test and a test command (in package.json, a Makefile or a tests/ folder), "
                    "or run setup again with the command: setup_check.py --tests \"<your test command>\".")
    facts["tests"] = command
    code, out = sh(command, offline=True)
    facts["test_network"] = False
    if code != 0:
        port, log, stop = watch_proxy()
        try:
            online, online_out = sh(command, net=True, port=port)
        finally:
            stop()
        hosts = sorted({l.split()[1] for l in open(log) if l.startswith("allowed ")}) if os.path.exists(log) else []
        facts["test_domains"] = hosts
        if online == 0:
            # Tests that reach the internet can run with Test network on: network open, home folder closed, no keys.
            facts["test_network"], code, out = True, online, online_out
            print(f"- Tests need the network: ask. `{command}` passes only online, calling {', '.join(hosts) or 'no named host'}. "
                  "With Test network on, the tests reach only the domains you allow, with no keys and the home folder "
                  "closed; off, every run stops before it starts.")
        elif sh(command, net=True)[0] == 0:
            return fail("Tests pass", f"`{command}` reaches the internet without going through a proxy (a raw socket, "
                        "or a client that ignores HTTPS_PROXY), so Dualtrack can't limit it to your domains.",
                        "make those tests use HTTP(S) clients that honour HTTPS_PROXY, or move them to CI under Required "
                        "checks, then run setup again.")
        elif sh(command)[0] == 0:
            return fail("Tests pass", f"`{command}` passes only with your own keys or settings, so it calls a live service.",
                        "move the tests that need keys to CI and name that CI check under Required checks, then run setup "
                        "again with setup_check.py --tests \"<the tests that need no keys>\".")
    n = tests_ran(out)
    # unittest (from Python 3.12) and pytest exit 5 when no test ran: that is no tests, not failing ones
    if n == 0 or (code == 5 and n is None and "no tests ran" in out.lower()):
        return fail("Tests pass", f"`{command}` ran 0 tests.", "add at least one test the command runs.")
    if code != 0:
        last = [l for l in out.strip().splitlines() if l.strip()][-3:]
        return fail("Tests pass", f"`{command}` fails on this branch: {' / '.join(last)}",
                    "make the tests pass on your default branch first. Dualtrack agents check every change against them. "
                    "If they fail because they need keys for a live service, move those tests to CI, name the CI "
                    "check under Required checks, and run setup again with setup_check.py --tests \"<the rest>\".")
    missed = unittest_misses(command)
    if missed:
        return fail("Tests pass", f"`{command}` passes, but unittest never runs plain test functions: {', '.join(missed[:5])}.",
                    "install pytest (`python3 -m pip install pytest`) so those run too, or move them into a unittest.TestCase.")
    ok("Tests pass", f"`{command}`, {n if n is not None else 'an unknown number of'} tests")
    # What is already built, so the first review starts from it. Never a stop: a repo with no issues still sets up.
    work = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "worklog.py")], capture_output=True, text=True)
    facts["work"] = (work.stdout.strip().splitlines() or ["work ledger: unknown"])[-1]
    print(f"- {facts['work']}")
    print(json.dumps(dict(facts, ok=True)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
