"""The live dashboard: records the owner's calls from this machine only, and refuses everything else."""
import http.client
import json
import os
import pathlib
import sys
import tempfile
import threading
import time
import unittest

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
import dashboard_server
import loop_lib
from tests.test_decide import MEMO
try:
    import scratch
except ImportError:  # run as tests.test_x from the repo root
    from tests import scratch


class Server(unittest.TestCase):
    def setUp(self):
        self.d = scratch.mkdtemp()
        self.cwd = os.getcwd()
        os.chdir(self.d)
        os.mkdir("ctx")
        pathlib.Path("profile.md").write_text("**Context path:** ctx\n")
        loop_lib.morning(MEMO, "waiting", "2026-11-03", "/kit", "ctx")
        self.server = dashboard_server.serve("profile.md")
        self.port = self.server.server_address[1]
        self.home = "/?k=" + getattr(dashboard_server.Handler, "secret", "")
        self.t = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.t.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        os.chdir(self.cwd)

    def test_a_silent_connection_does_not_hold_the_server(self):
        import socket
        stuck = socket.create_connection(("127.0.0.1", self.port)); stuck.sendall(b"GET / HT")
        try:
            start = time.monotonic()
            self.assertEqual(self.request("GET", self.home)[0], 200)
            self.assertLess(time.monotonic() - start, 15)
        finally:
            stuck.close()

    def request(self, method, path, body=None, **headers):
        base = {"Host": f"127.0.0.1:{self.port}", "Origin": f"http://127.0.0.1:{self.port}",
                "Content-Type": "application/json", "X-Dualtrack-Token": dashboard_server.Handler.token}
        base.update({k.replace("_", "-"): v for k, v in headers.items()})
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        c.putrequest(method, path, skip_host=True)
        for k, v in base.items():
            if v is not None:
                c.putheader(k, v)
        data = json.dumps(body).encode() if body is not None else b""
        c.putheader("Content-Length", str(len(data)))
        c.endheaders(data)
        r = c.getresponse()
        return r.status, r.read().decode(), dict(r.getheaders())

    def records(self):
        return {p.name: p.read_bytes() for p in pathlib.Path("ctx").iterdir()}

    def test_a_pick_is_recorded_and_the_page_then_offers_undo(self):
        status, page, headers = self.request("GET", self.home)
        self.assertEqual(status, 200)
        self.assertIn('name=dualtrack-live content="', page)
        self.assertIn("Each button records your call", page)
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        status, body, _ = self.request("POST", "/call", {"argv": ["2", json.load(open("ctx/options.json"))["table"]]})
        self.assertEqual((status, json.loads(body)["code"]), (200, 0))
        self.assertEqual(loop_lib.confirmed(pathlib.Path("ctx/bets.md").read_text()), "Fix the install step")
        page = self.request("GET", self.home)[1]
        self.assertIn("You picked <em>Fix the install step</em>", page)
        self.assertNotIn("Pick the next change", page)  # the brief is answered, so its card is gone
        self.assertEqual(json.loads(self.request("POST", "/call", {"argv": ["undo", "Fix the install step"]})[1])["code"], 0)
        page = self.request("GET", self.home)[1]
        self.assertIn("Pick the next change", page)  # undone, the choice is open again
        self.assertNotIn("You picked", page)

    def test_the_board_hands_a_bet_on_signed_by_the_profiles_owner(self):
        pathlib.Path("profile.md").write_text("**Context path:** ctx\n\n**Owner:** Ana\n")
        self.request("POST", "/call", {"argv": ["2", json.load(open("ctx/options.json"))["table"]]})
        self.assertIn('data-kind="owner"', self.request("GET", self.home)[1])
        status, body, _ = self.request("POST", "/call", {"argv": ["owner", "Fix the install step", "Sam"]})
        self.assertEqual((status, json.loads(body)["code"]), (200, 0))
        bets = pathlib.Path("ctx/bets.md").read_text()
        self.assertIn("| Fix the install step | owner: Sam | by: Ana\n", bets)
        self.assertEqual(loop_lib.owners(bets)["fix the install step"], "Sam")

    def test_a_refused_call_runs_nothing(self):
        before = self.records()
        token = dashboard_server.Handler.token
        for why, body, headers in [
            ("no token", {"argv": ["2"]}, {"X_Dualtrack_Token": None}),
            ("bad token", {"argv": ["2"]}, {"X_Dualtrack_Token": "x" * len(token)}),
            ("other origin", {"argv": ["2"]}, {"Origin": "http://evil.example"}),
            ("no origin", {"argv": ["2"]}, {"Origin": None}),
            ("rebinding host", {"argv": ["2"]}, {"Host": f"evil.example:{self.port}"}),
            ("form post", {"argv": ["2"]}, {"Content_Type": "text/plain"}),
            ("not a call", {"argv": ["note", "x"]}, {}),
            ("shell text", {"argv": "2; rm -rf ."}, {}),
            ("newline", {"argv": ["try", "a\nb"]}, {}),
            ("empty", {"argv": []}, {}),
            ("names its own signer", {"argv": ["try", "--by", "Sam", "x"]}, {}),
        ]:
            with self.subTest(why):
                status, body, _ = self.request("POST", "/call", body, **headers)
                self.assertEqual(status, 403, why)
                self.assertIn("Nothing was recorded", body)
                self.assertEqual(self.records(), before, why)  # byte for byte
        self.assertEqual(self.request("GET", "/", Host="evil.example")[0], 403)

    def test_the_page_and_token_need_the_launch_secret(self):
        token = dashboard_server.Handler.token
        for why, path in [("bare", "/"), ("wrong k", "/?k=" + "x" * 43), ("empty k", "/?k="), ("k elsewhere", "/other?k=" + self.home[3:])]:
            with self.subTest(why):
                status, body, _ = self.request("GET", path)
                self.assertEqual(status, 403, why)
                self.assertNotIn(token, body)
        status, body, _ = self.request("GET", self.home)
        self.assertEqual(status, 200)
        self.assertIn(token, body)
        self.assertNotEqual(self.home[3:], token)  # the secret is not the token

    def test_a_post_still_needs_the_token_even_with_the_secret(self):
        before = self.records()
        status, body, _ = self.request("POST", "/call?k=" + self.home[3:], {"argv": ["2"]}, X_Dualtrack_Token=None)
        self.assertEqual(status, 403)
        self.assertEqual(self.records(), before)

    def test_a_token_that_is_not_ascii_is_refused_not_a_crash(self):
        before = self.records()
        status, _, _ = self.request("POST", "/call", {"argv": ["2"]}, X_Dualtrack_Token="é")
        self.assertEqual(status, 403)
        self.assertEqual(self.records(), before)

    def test_a_refusal_from_decide_is_said_not_hidden(self):
        before = self.records()
        status, body, _ = self.request("POST", "/call", {"argv": ["undo", "Never picked"]})
        r = json.loads(body)
        self.assertEqual(r["code"], 4)
        self.assertIn("nothing to undo", r["output"])
        self.assertEqual(self.records(), before)


class Launch(unittest.TestCase):
    def test_the_launch_secret_is_never_on_a_browser_launchers_argv(self):
        from unittest import mock
        opened, hop = [], {}
        real = os.unlink
        keep = lambda p: hop.update(text=open(p).read(), mode=os.stat(p).st_mode & 0o777) or real(p)
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(os.environ, {"DUALTRACK_HOME": home}), \
                mock.patch("webbrowser.open", lambda u: opened.append(u) or True), mock.patch("sys.stdout"), \
                mock.patch.object(dashboard_server, "IDLE", 0), mock.patch.object(dashboard_server.decide, "find_profile", lambda: __file__), \
                mock.patch.object(dashboard_server.os, "unlink", keep):
            self.assertEqual(dashboard_server.main(), 0)
        self.assertEqual(len(opened), 1)
        self.assertNotIn("k=", opened[0])  # argv is world-readable in ps
        self.assertTrue(opened[0].startswith("file://"))
        self.assertIn(dashboard_server.Handler.secret, hop["text"])  # the secret rides in the private file
        self.assertEqual(hop["mode"], 0o600)


class Allowed(unittest.TestCase):
    def test_only_the_owners_calls_pass(self):
        for argv in (["1"], ["allow"], ["resume"], ["2", "ab12"], ["try", "x"], ["no", "x"], ["answer", "x"], ["result", "t", "helped"], ["undo", "t"], ["owner", "t", "Sam"], ["try", "a\tb ✓ 👩‍💻"]):
            self.assertTrue(dashboard_server.allowed(argv), argv)
        for argv in (None, "2", [], [2], ["allow", "x"], ["resume", "x"], ["done", "1", "x"], ["--from-doc"], ["-1"], ["note", "x"],
                     ["owner", "t"], ["owner", "t", " "], ["owner", "t", "Sam", "x"],
                     ["areas"], ["areas", "no"], ["try", "a", "b", "c", "d", "e"], ["try", "a\0b"], ["try", "a\rb"], ["try", "a\u2028b"], ["try", "a\x85b"], ["answer", "\x1b[31mx"], ["try", "x" * 2000],
                     ["try", "--by", "Sam", "x"], ["--by", "Sam", "2"], ["owner", "t", "--by"]):  # the page never names its signer
            self.assertFalse(dashboard_server.allowed(argv), argv)


if __name__ == "__main__":
    unittest.main()
