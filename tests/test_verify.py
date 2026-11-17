"""verify.py and release.sh: a copy of Dualtrack is checked against the maker's signature. The keys here are throwaway test keys."""
import os
import pathlib
import shutil
import subprocess
import sys
import unittest

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
import verify
try:
    import scratch
except ImportError:  # run as tests.test_x from the repo root
    from tests import scratch

HAVE_SSH = shutil.which("ssh-keygen") is not None


def sh(*a, cwd=None, **kw):
    return subprocess.run(a, cwd=cwd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60, **kw)


def key(d, name):
    sh("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(d / name))
    return d / name, " ".join((d / f"{name}.pub").read_text().split()[:2])


def repo(d):
    r = d / "kit"
    (r / "scripts").mkdir(parents=True)
    (r / "agents.md").write_text("decline harm\n")
    (r / "scripts/guards.sh").write_text("echo guard\n")
    for c in (["init", "-q", "-b", "main"], ["config", "user.name", "t"], ["config", "user.email", "t@example.invalid"]):
        sh("git", *c, cwd=r)
    return r


@unittest.skipUnless(HAVE_SSH, "ssh-keygen is needed")
class Verify(unittest.TestCase):
    def setUp(self):
        self.d = pathlib.Path(scratch.mkdtemp())
        self.kit = repo(self.d)
        self.priv, self.pub = key(self.d, "release")
        (self.kit / "release-signers").write_text(f"{verify.NAMESPACE} {self.pub}\n")
        sh("git", "add", "-A", cwd=self.kit); sh("git", "commit", "-qm", "init", cwd=self.kit)
        self.manifest = self.d / "RELEASE-MANIFEST"
        self.manifest.write_text(verify.manifest(str(self.kit)))
        self.sign(self.priv)

    def sign(self, priv):
        pathlib.Path(str(self.manifest) + ".sig").unlink(missing_ok=True)  # ssh-keygen will not overwrite a signature
        sh("ssh-keygen", "-Y", "sign", "-f", str(priv), "-n", verify.NAMESPACE, str(self.manifest))

    def check(self):
        return verify.verify(str(self.kit), str(self.manifest), str(self.manifest) + ".sig")

    def test_a_release_checkout_passes_and_says_who_signed_it(self):
        ok, said = self.check()
        self.assertTrue(ok, said)
        self.assertIn("SHA256:", said)

    def test_one_changed_byte_fails_and_names_the_file(self):
        p = self.kit / "scripts/guards.sh"
        p.write_bytes(p.read_bytes().replace(b"guard", b"guarD"))
        ok, said = self.check()
        self.assertFalse(ok)
        self.assertIn("scripts/guards.sh", said)

    def test_an_added_file_fails(self):
        (self.kit / "extra.py").write_text("x\n")
        self.assertFalse(self.check()[0])

    def test_a_planted_pyc_fails(self):
        # an unchecked-hash .pyc runs in place of the source it sits beside
        (self.kit / "scripts/__pycache__").mkdir()
        (self.kit / "scripts/__pycache__/guards.cpython-314.pyc").write_bytes(b"\x00")
        ok, said = self.check()
        self.assertFalse(ok)
        self.assertIn("__pycache__", said)

    def test_a_manifest_signed_by_another_key_fails(self):
        other, _ = key(self.d, "fork")
        self.sign(other)  # a fork signs its own copy; the release key does not match
        ok, said = self.check()
        self.assertFalse(ok)
        self.assertIn("not signed by the Dualtrack release key", said)

    def test_an_edited_manifest_fails_the_signature(self):
        self.manifest.write_text(self.manifest.read_text().replace("a", "b", 1))
        self.assertFalse(self.check()[0])

    def test_no_signers_file_fails_closed(self):
        (self.kit / "release-signers").unlink()
        ok, said = self.check()
        self.assertFalse(ok)
        self.assertIn("no release key", said)

    def test_the_command_exits_zero_on_a_release_and_four_on_a_changed_byte(self):
        args = [sys.executable, str(KIT / "scripts/verify.py"), str(self.kit), "--manifest", str(self.manifest), "--sig", str(self.manifest) + ".sig"]
        self.assertEqual(sh(*args).returncode, 0)
        (self.kit / "agents.md").write_text("decline harm\n ")
        self.assertEqual(sh(*args).returncode, 4)

    def test_release_signs_the_tag_and_the_manifest_and_refuses_without_a_key(self):
        shutil.copy(KIT / "scripts/verify.py", self.kit / "scripts/verify.py")
        shutil.copy(KIT / "scripts/release.sh", self.kit / "scripts/release.sh")
        sh("git", "add", "-A", cwd=self.kit); sh("git", "commit", "-qm", "scripts", cwd=self.kit)
        no_key = sh("bash", "scripts/release.sh", "v0.0.1", cwd=self.kit, env={k: v for k, v in os.environ.items() if k != "SIGNING_KEY"})
        self.assertNotEqual(no_key.returncode, 0)
        self.assertEqual(sh("git", "tag", cwd=self.kit).stdout.strip(), "")
        r = sh("bash", "scripts/release.sh", "v0.0.1", cwd=self.kit, env=dict(os.environ, SIGNING_KEY=str(self.priv)))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        signers = self.d / "git-signers"
        signers.write_text(f"* {self.pub}\n")
        tag = sh("git", "-c", f"gpg.ssh.allowedSignersFile={signers}", "-c", "gpg.format=ssh", "tag", "-v", "v0.0.1", cwd=self.kit)
        self.assertEqual(tag.returncode, 0, tag.stdout + tag.stderr)
        self.assertIn("To publish:", r.stdout)


class Docs(unittest.TestCase):
    def test_the_release_steps_and_the_readme_name_signing_and_verifying(self):
        steps = (KIT / "docs/release.md").read_text()
        for want in ("release.sh", "verify.py", "release-signers", "fingerprint"):
            self.assertIn(want, steps)
        self.assertIn("docs/release.md", (KIT / "README.md").read_text())


if __name__ == "__main__":
    unittest.main()
