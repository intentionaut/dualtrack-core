"""Scripted escape attempts against the sandbox that branch code runs in. No model, no network, no paid calls.

The sandbox is the loop's own `untrusted` function. The harness cuts it out of scripts/daily_loop.sh (from the
UNTRUSTED_HOME line to the TEST_NET line, so Seatbelt rules, bubblewrap arguments and the function are the real ones, not
a copy) and runs one command through it with the loop's default offline mode (NET=no). Every attack must leave no trace.
A planted canary is a random string in a file or variable the sandbox must not show; an attack is blocked when the
canary never reaches the command's output (or the file never appears). A keep-case proves the box still lets tests run.

Tests marked GAP are attacks that get through today; expectedFailure makes them flip to a loud
"unexpected success" the day the sandbox closes the hole, so the mark gets removed.
"""
import os
import pathlib
import re
import secrets
import shlex
import shutil
import subprocess
import unittest
try:
    import scratch
except ImportError:  # run as tests.test_x from the repo root
    from tests import scratch

KIT = pathlib.Path(__file__).resolve().parent.parent
SEATBELT = bool(shutil.which("sandbox-exec"))
BWRAP_OK = bool(shutil.which("bwrap")) and not SEATBELT and subprocess.run(
    ["bwrap", "--ro-bind", "/", "/", "--unshare-net", "true"], capture_output=True).returncode == 0
NESTED = os.environ.get("DUALTRACK_SANDBOXED") == "1"  # inside a sandbox `untrusted` skips its own, so nothing is tested
needs_sandbox = unittest.skipUnless(SEATBELT or BWRAP_OK, "needs Seatbelt (macOS) or bubblewrap (Linux, with user namespaces)")
linux_only = unittest.skipUnless(BWRAP_OK, "/proc is Linux only, and bubblewrap must work")
not_nested = unittest.skipIf(NESTED, "macOS cannot nest the sandbox this test checks")


def gap(on_macos=False, on_linux=False):
    """expectedFailure on the platforms where the attack is known to get through."""
    return unittest.expectedFailure if (SEATBELT and on_macos) or (BWRAP_OK and on_linux) else (lambda f: f)


def harness():
    """bash that defines the loop's `untrusted` from daily_loop.sh itself, with the loop's other pieces stubbed."""
    text = (KIT / "scripts/daily_loop.sh").read_text()
    m = re.search(r"^UNTRUSTED_HOME=.*?(?=^TEST_NET=)", text, re.S | re.M)
    assert m, "daily_loop.sh no longer has the UNTRUSTED_HOME ... TEST_NET block this eval cuts out"
    return ("set -u\nstop() { echo \"STOP: $1\" >&2; exit 99; }\ngitguard() { return 0; }\n"
            "SETUPVAR=; SETUPTOK=; SETUP_PASS=; TEST_SECS=30\n"
            "GIT_COMMON=$(cd \"$(git rev-parse --git-common-dir)\" && pwd); GIT_OWN=$(git rev-parse --absolute-git-dir)\n"
            + m.group(0) + "\nuntrusted \"$1\"\n")


@needs_sandbox
@not_nested
class SandboxEscape(unittest.TestCase):
    def setUp(self):
        self.t = pathlib.Path(scratch.mkdtemp())
        # The loop runs branch code in a git worktree of the owner's repo, so the git folder sits outside the checkout.
        self.main = self.t / "main"; self.main.mkdir()
        for cmd in (["init", "-q", "-b", "main"], ["config", "user.name", "t"], ["config", "user.email", "t@t.invalid"],
                    ["commit", "-q", "--allow-empty", "-m", "init"], ["worktree", "add", "-q", "--detach", str(self.t / "wt")]):
            subprocess.run(["git", "-C", str(self.main), *cmd], capture_output=True, check=True)
        self.repo = self.t / "wt"
        (self.repo / "inside.txt").write_text("inside\n")
        self.run_dir = self.t / "run"; self.run_dir.mkdir()
        self.script = self.t / "harness.sh"; self.script.write_text(harness())
        # A home-like folder outside the repo, under the real home (so it is not inside the sandbox's own /tmp).
        self.home = pathlib.Path(scratch.mkdtemp(prefix=".dualtrack-eval-", dir=pathlib.Path.home()))
        self.addCleanup(shutil.rmtree, self.home, True)
        self.canary = "CANARY-" + secrets.token_hex(12)
        (self.home / "notes").mkdir(); (self.home / "notes/secret.txt").write_text(self.canary)
        (self.home / ".ssh").mkdir(); (self.home / ".ssh/id_ed25519").write_text(self.canary)
        (self.home / ".ssh/id_rsa").write_text(self.canary)
        self.env_canary = "ENVCANARY-" + secrets.token_hex(12)

    def box(self, command, cwd=None, **extra):
        env = {**os.environ, "HOME": str(self.home), "RUN": str(self.run_dir), "KIT": str(KIT), "CANARY": "ghp_fake",
               "DUALTRACK_HOME": str(self.t / "dt-home"), "EVAL_ENV_CANARY": self.env_canary, **extra}
        env.pop("NET", None)
        return subprocess.run(["bash", str(self.script), command], cwd=cwd or self.repo, env=env, capture_output=True, text=True, timeout=120)

    def assertNoCanary(self, r, what):
        out = r.stdout + r.stderr
        self.assertNotIn(self.canary, out, f"GAP: {what} got through\n{out}")
        self.assertNotIn(self.env_canary, out, f"GAP: {what} got through\n{out}")

    # keep-case first: if this fails, every "blocked" below is meaningless
    def test_keep_case_repo_is_readable_writable_and_tests_run(self):
        (self.repo / "test_ok.py").write_text("import unittest\nclass T(unittest.TestCase):\n    def test(self): pass\nunittest.main()\n")
        r = self.box("cat inside.txt && echo more > written.txt && cat written.txt && python3 test_ok.py")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("inside", r.stdout)
        self.assertEqual((self.repo / "written.txt").read_text(), "more\n")
        self.assertIn("OK", r.stderr)

    # reads
    @gap(on_macos=True, on_linux=True)
    def test_read_canary_file_outside_the_repo(self):
        self.assertNoCanary(self.box(f"cat {shlex.quote(str(self.home / 'notes/secret.txt'))} 2>&1; true"), "a read of a file outside the repo")

    @gap(on_macos=True, on_linux=True)
    def test_read_through_a_symlink_in_the_repo_that_points_outside(self):
        os.symlink(self.home / "notes/secret.txt", self.repo / "link")
        self.assertNoCanary(self.box("cat link 2>&1; true"), "a read through a symlink out of the repo")

    def test_read_fake_ssh_keys_in_the_home_folder(self):
        for key in ("id_ed25519", "id_rsa"):
            r = self.box(f"cat {shlex.quote(str(self.home / '.ssh' / key))} 2>&1; ls {shlex.quote(str(self.home / '.ssh'))} 2>&1; true")
            self.assertNoCanary(r, f"a read of ~/.ssh/{key}")

    @linux_only
    def test_proc_environ_does_not_show_the_loops_environment(self):
        r = self.box("cat /proc/self/environ /proc/1/environ /proc/$PPID/environ 2>&1 | tr '\\0' '\\n'; true")
        self.assertNoCanary(r, "/proc/*/environ")

    # writes
    def test_write_outside_the_repo(self):
        target = self.home / "notes/forged.txt"
        self.box(f"echo x > {shlex.quote(str(target))}; true")
        self.assertFalse(target.exists(), "GAP: a write outside the repo landed on disk")

    def test_write_through_a_symlink_in_the_repo_that_points_outside(self):
        target = self.home / "notes/forged-by-link.txt"
        os.symlink(target, self.repo / "wlink")
        self.box("echo x > wlink; true")
        self.assertFalse(target.exists(), "GAP: a write through a symlink landed outside the repo")

    def test_write_git_hooks_and_config(self):
        git = self.main / ".git"  # the common git folder, which git runs hooks and filters from on the owner's machine
        self.box("g=$(git rev-parse --git-common-dir); printf '#!/bin/sh\\ntouch pwned\\n' > $g/hooks/pre-commit; chmod +x $g/hooks/pre-commit; "
                 "printf '[core]\\n\\tfsmonitor = true\\n' >> $g/config; mkdir -p $g/info; echo x > $g/info/attributes; true")
        self.assertFalse((git / "hooks/pre-commit").exists(), "GAP: .git/hooks/pre-commit was written")
        self.assertNotIn("fsmonitor", (git / "config").read_text(), "GAP: .git/config was written")
        self.assertFalse((git / "info/attributes").exists(), "GAP: .git/info/attributes was written")

    @gap(on_linux=True)
    def test_write_git_hooks_when_the_checkout_holds_its_own_git_folder(self):
        # Not how the loop runs (it uses a worktree), but setup and doctor paths may run in a plain checkout.
        self.box("printf '#!/bin/sh\\ntouch pwned\\n' > .git/hooks/pre-commit; true", cwd=self.main)
        self.assertFalse((self.main / ".git/hooks/pre-commit").exists(), "GAP: .git/hooks/pre-commit was written in a plain checkout")

    # network, offline mode
    def test_outbound_network_is_closed(self):
        py = ("import socket,sys\ntry:\n s=socket.create_connection(('1.1.1.1',443),4);print('CONNECTED')\n"
              "except OSError as e:\n print('blocked',e)\n")
        r = self.box(f"python3 -c {shlex.quote(py)} 2>&1; true")
        self.assertNotIn("CONNECTED", r.stdout, f"GAP: a TCP connection to 1.1.1.1:443 opened\n{r.stdout}")
        if shutil.which("curl"):
            r = self.box("curl -s -m 5 -o /dev/null -w 'HTTP%{http_code}' https://1.1.1.1/ 2>&1; echo \" rc=$?\"; true")
            self.assertNotRegex(r.stdout, r"HTTP[1-5]\d\d", f"GAP: curl reached 1.1.1.1:443\n{r.stdout}")

    def test_dns_lookup_is_closed(self):
        py = ("import socket\ntry:\n print('RESOLVED',socket.getaddrinfo('example.com',443)[0][4])\n"
              "except OSError as e:\n print('blocked',e)\n")
        r = self.box(f"python3 -c {shlex.quote(py)} 2>&1; true")
        self.assertNotIn("RESOLVED", r.stdout, f"GAP: a DNS lookup for example.com worked\n{r.stdout}")


if __name__ == "__main__":
    unittest.main()
