import base64
import json
import pathlib
import subprocess
import sys
import unittest
from unittest import mock

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
import app_token
try:
    import scratch
except ImportError:  # run as tests.test_x from the repo root
    from tests import scratch


def unb64(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class AppToken(unittest.TestCase):
    def setUp(self):
        self.t = pathlib.Path(scratch.mkdtemp())
        self.key = self.t / "app.pem"
        subprocess.run(["openssl", "genrsa", "-out", str(self.key), "2048"], capture_output=True, check=True)
        subprocess.run(["openssl", "rsa", "-in", str(self.key), "-pubout", "-out", str(self.t / "pub.pem")], capture_output=True, check=True)

    def test_the_jwt_is_signed_by_the_apps_key_and_lives_under_ten_minutes(self):
        token = app_token.jwt(123, str(self.key), now=1_000_000)
        head, body, sig = token.split(".")
        claims = json.loads(unb64(body))
        self.assertEqual(claims["iss"], "123")
        self.assertLessEqual(claims["exp"] - claims["iat"], 600)
        (self.t / "sig").write_bytes(unb64(sig))
        ok = subprocess.run(["openssl", "dgst", "-sha256", "-verify", str(self.t / "pub.pem"), "-signature", str(self.t / "sig")],
                            input=f"{head}.{body}".encode(), capture_output=True)
        self.assertEqual(ok.returncode, 0, ok.stdout)

    def test_a_vault_signer_signs_and_the_key_is_never_read(self):
        # The signer stands in for a cloud KMS: the loop hands it bytes and gets a signature back.
        signer = f"openssl dgst -sha256 -sign {self.key}"
        head, body, sig = app_token.jwt(7, None, now=1_000_000, signer=signer).split(".")
        (self.t / "sig").write_bytes(unb64(sig))
        ok = subprocess.run(["openssl", "dgst", "-sha256", "-verify", str(self.t / "pub.pem"), "-signature", str(self.t / "sig")],
                            input=f"{head}.{body}".encode(), capture_output=True)
        self.assertEqual(ok.returncode, 0)

    def test_the_token_is_for_one_repo_and_only_what_the_loop_needs(self):
        calls = []
        def call(url, token, data=None):
            calls.append((url, data))
            return {"id": 9, "permissions": dict(app_token.PERMISSIONS)} if url.endswith("/installation") else {"token": "ghs_x"}
        with mock.patch.object(app_token, "call", call):
            self.assertEqual(app_token.token("acme/shop", {"DUALTRACK_APP_ID": "1", "DUALTRACK_APP_KEY": str(self.key)}), "ghs_x")
        url, data = calls[1]
        self.assertTrue(url.endswith("/app/installations/9/access_tokens"))
        self.assertEqual(data["repositories"], ["shop"])
        self.assertEqual(data["permissions"]["administration"], "read")  # rules to read, never to change
        for never in ("workflows", "secrets", "actions"):
            self.assertNotIn(never, data["permissions"])

    def test_a_missing_grant_narrows_the_token_and_says_so(self):
        notes = []
        got = app_token.wanted({"contents": "write", "pull_requests": "write", "issues": "write", "checks": "read",
                                "statuses": "read", "metadata": "read"}, notes.append)
        self.assertEqual(got["checks"], "read"); self.assertNotIn("administration", got)
        self.assertEqual(len(notes), 2); self.assertIn("checks", notes[0])

    def test_no_app_settings_says_what_is_missing(self):
        r = subprocess.run([sys.executable, str(KIT / "scripts/app_token.py"), "acme/shop"], capture_output=True, text=True,
                           env={"PATH": "/usr/bin:/bin"})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("DUALTRACK_APP_SIGNER or DUALTRACK_APP_KEY", r.stderr)


if __name__ == "__main__":
    unittest.main()
