"""Encoded token exfiltration: a fake GitHub token, hidden nine ways, must be caught on every outbound path.

Paths: the scan itself (loop_lib.leaks, also used by the MCP server, handoff and preview), a pull request body or
source output (the CLI's `leaks` on a file), a public pull request's text (`public-text`), a commit's diff and a
commit message (the `git log -p` scan in daily_loop.sh), and release notes (loop_lib.notes). A form that gets
through is an expected failure marked GAP, not a fix: the scanners are unchanged here.
"""
import base64
import gzip
import os
import pathlib
import subprocess
import sys
import tempfile
import unicodedata
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import loop_lib

LIB = str(ROOT / "scripts" / "loop_lib.py")
# Obviously fake: a fixed pattern, never a real token.
CANARY = "ghp_" + "Ab1Cd2Ef3Gh4Ij5Kl6Mn7Op8Qr9St0Uv1Wx2"
ZWSP = "​"


def _b64(s):
    return base64.b64encode(s.encode()).decode()


def _b64url(s):
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


FORMS = {
    "plaintext": lambda c: "GITHUB_TOKEN=" + c,
    "base64": lambda c: "debug: " + _b64(c),
    "base64url": lambda c: "debug: " + _b64url(c),
    "hex": lambda c: "debug: " + c.encode().hex(),
    "url_encoded": lambda c: "debug: " + "".join("%%%02x" % b for b in c.encode()),
    "reversed": lambda c: "debug: " + c[::-1],
    "split_two_lines": lambda c: "debug: " + c[:20] + "\n" + c[20:],
    "spaced": lambda c: "debug: " + " ".join(c),
    "zero_width": lambda c: "debug: " + ZWSP.join(c),
    "gzip_base64": lambda c: "debug: " + base64.b64encode(gzip.compress(c.encode())).decode(),
}

# Ordinary text that looks encoded and must never be flagged.
PNG_BODY = base64.b64encode(bytes((i * 37 + 11) % 256 for i in range(900))).decode()
KEPT = {
    "image_data_uri": "![x](data:image/png;base64," + PNG_BODY + ")",
    "git_sha_1": "Merge commit e0e6d3b5a1c2f4d6789012345678901234567890 into main",
    "git_sha_256": "sha256:" + "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    "npm_integrity": "integrity sha512-" + base64.b64encode(bytes((i * 7) % 256 for i in range(64))).decode(),
    "base64_prose": "notes: " + _b64("The quick brown fox jumps over the lazy dog, twice, for the release notes."),
    "hex_prose": "dump: " + "Release notes for the product team, version one.".encode().hex(),
    "url_encoded_prose": "see https://example.com/?q=" + "".join("%%%02x" % b for b in b"hello world, nothing here"),
    "uuid": "run 123e4567-e89b-12d3-a456-426614174000 finished",
    "long_identifier": "call " + "a" * 30 + "_" + "b" * 30,
}


def run_cli(*args):
    return subprocess.run([sys.executable, LIB] + list(args), capture_output=True, text=True)


def via_leaks(text):
    return bool(loop_lib.leaks(text))


def via_file(text):
    """A pull request body or a source's output, scanned as a file."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "body.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return run_cli("leaks", p).returncode == 4


def via_public_text(text):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "public-text.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return run_cli("public-text", p, d).returncode == 4


def via_notes(text):
    return "a secret" in loop_lib.notes(text, house=False)


_REPO = {}


def _git(*args, cwd):
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_TERMINAL_PROMPT="0")
    cfg = ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=" + os.devnull]
    return subprocess.run(["git"] + cfg + list(args), cwd=cwd, env=env, capture_output=True, text=True, check=True).stdout


def _scan_last_commit(repo):
    # The same read daily_loop.sh does before a push: every commit's patch and message.
    out = _git("log", "-p", "--text", "--no-ext-diff", "--no-textconv", "--no-renames", "--format=%B", "-1", cwd=repo)
    return via_file(out)


def via_diff(text):
    repo = _REPO["dir"].name
    _REPO["n"] = _REPO.get("n", 0) + 1
    name = "f%d.txt" % _REPO["n"]  # a new file each time, so an earlier case's lines are not in this diff
    with open(os.path.join(repo, name), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    _git("add", name, cwd=repo)
    _git("commit", "-q", "-m", "change", cwd=repo)
    return _scan_last_commit(repo)


def via_commit_message(text):
    repo = _REPO["dir"].name
    _git("commit", "-q", "--allow-empty", "-m", text, cwd=repo)
    return _scan_last_commit(repo)


PATHS = {
    "leaks_fn": via_leaks,
    "pr_body_or_source": via_file,
    "public_text": via_public_text,
    "diff": via_diff,
    "commit_message": via_commit_message,
    "release_notes": via_notes,
}

# GAP cells: (form, path) the scanners miss today. Recorded, not fixed here; remove a cell when its scanner learns the form.
GAPS = {
    ("gzip_base64", "leaks_fn"),
    ("gzip_base64", "pr_body_or_source"),
    ("gzip_base64", "public_text"),
    ("gzip_base64", "diff"),
    ("gzip_base64", "commit_message"),
    ("gzip_base64", "release_notes"),
    ("reversed", "leaks_fn"),
    ("reversed", "pr_body_or_source"),
    ("reversed", "public_text"),
    ("reversed", "diff"),
    ("reversed", "commit_message"),
    ("reversed", "release_notes"),
    ("spaced", "leaks_fn"),
    ("spaced", "pr_body_or_source"),
    ("spaced", "public_text"),
    ("spaced", "diff"),
    ("spaced", "commit_message"),
    ("spaced", "release_notes"),
    ("split_two_lines", "leaks_fn"),
    ("split_two_lines", "pr_body_or_source"),
    ("split_two_lines", "public_text"),
    ("split_two_lines", "diff"),
    ("split_two_lines", "commit_message"),
    ("split_two_lines", "release_notes"),
    ("base64", "release_notes"),
    ("base64url", "release_notes"),
    ("hex", "release_notes"),
    ("url_encoded", "release_notes"),
    ("zero_width", "release_notes"),
}


class EncodedExfil(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _REPO["dir"] = tempfile.TemporaryDirectory()
        _git("init", "-q", cwd=_REPO["dir"].name)

    @classmethod
    def tearDownClass(cls):
        _REPO["dir"].cleanup()
        _REPO.clear()

    def test_canary_is_caught_in_plain_form_by_the_shape_it_claims(self):
        self.assertEqual(len(CANARY), 40)
        self.assertEqual(loop_lib.leaks(CANARY), ["a secret"])

    def test_kept_cases_pass_every_path(self):
        for name, text in KEPT.items():
            for path, scan in PATHS.items():
                self.assertFalse(scan(text), "false positive: %s on %s" % (name, path))

    def test_kept_cases_beside_the_canary_do_not_hide_it(self):
        text = "\n".join(KEPT.values()) + "\n" + FORMS["plaintext"](CANARY)
        for path, scan in PATHS.items():
            self.assertTrue(scan(text), path)

    def test_repo_files_are_not_flagged_by_decoding(self):
        """False-positive measure on this repo's own tracked text: no file may be flagged only because a
        base64, hex or %-encoded run in it decodes to a secret. (Five files hold fake tokens in plain text,
        as test fixtures and the canary maker; those are true hits and are not counted.)"""
        files = subprocess.run(["git", "ls-files"], cwd=str(ROOT), capture_output=True, text=True, check=True).stdout.split("\n")
        flagged = []
        for rel in files:
            p = ROOT / rel
            if not rel or not p.is_file():
                continue
            try:
                data = p.read_bytes()
            except OSError:
                continue
            if b"\0" in data:
                continue
            text = data.decode("utf-8", "replace")
            if loop_lib.leaks(text) and not loop_lib._secret("".join(c for c in text if unicodedata.category(c) != "Cf")):
                flagged.append(rel)
        self.assertEqual(flagged, [])


def _make(form, path):
    def test(self):
        self.assertTrue(PATHS[path](FORMS[form](CANARY)), "%s not caught on %s" % (form, path))
    test.__doc__ = "%s, %s" % (form, path)
    if (form, path) in GAPS:
        test.__doc__ = "GAP: %s, %s" % (form, path)
        test = unittest.expectedFailure(test)
    return test


for _form in FORMS:
    for _path in PATHS:
        setattr(EncodedExfil, "test_%s__%s" % (_form, _path), _make(_form, _path))


if __name__ == "__main__":
    unittest.main()
