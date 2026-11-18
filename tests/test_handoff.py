import datetime
import hashlib
import hmac
import http.server
import json
import pathlib
import subprocess
import sys
import threading
import unittest

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
import handoff
try:
    import scratch
except ImportError:  # run as tests.test_x from the repo root
    from tests import scratch


class Catch(http.server.BaseHTTPRequestHandler):
    got = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        Catch.got.append((dict(self.headers), body))
        self.send_response(200); self.end_headers()

    def log_message(self, *a):
        pass


class Handoff(unittest.TestCase):
    def setUp(self):
        self.t = pathlib.Path(scratch.mkdtemp())
        self.ctx = self.t / "ctx"; self.ctx.mkdir()
        self.profile = self.t / "profile.md"
        self.profile.write_text(f"**Product:** Shop\n\n**Goal:** more repeat orders\n\n**Context path:** {self.ctx}\n")
        (self.ctx / "options.json").write_text(json.dumps({"date": "2026-11-06", "options": [{"change": "Fix checkout copy"}], "question": ""}))
        (self.ctx / "bets.md").write_text("- 2026-11-05 | Fix checkout copy | confirmed by owner\n")
        (self.ctx / "team-log.md").write_text("- 2026-11-06 | opened: Fix checkout copy, https://github.com/o/r/pull/7, x | $1.20\n")
        Catch.got = []

    def test_the_context_pack_carries_what_another_agent_needs(self):
        c = handoff.context(str(self.profile))
        self.assertEqual(c["schema"], "dualtrack.context.v1")
        self.assertEqual((c["product"], c["goal"], c["confirmed_bet"]), ("Shop", "more repeat orders", "Fix checkout copy"))
        self.assertEqual(c["options"][0]["change"], "Fix checkout copy")
        self.assertIn("decide.py try", c["steer"]["ask for something"])

    def test_an_event_is_written_and_names_the_pull_request(self):
        r = subprocess.run([sys.executable, str(KIT / "scripts/handoff.py"), "event", str(self.profile),
                            "opened: Fix checkout copy, https://github.com/o/r/pull/7, navigator APPROVE"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        ev = json.loads(next((self.ctx / "events").glob("*.json")).read_text())
        self.assertEqual((ev["schema"], ev["kind"], ev["pull_request"]), ("dualtrack.run.v1", "opened", "https://github.com/o/r/pull/7"))

    def test_mondays_event_carries_the_weekly_summary_and_other_days_do_not(self):
        (self.ctx / "weekly.md").write_text("## This week, to 2026-11-09\n\n- **Spend (estimated):** $1.00\n")
        monday = datetime.datetime(2026, 11, 9, 7, 0)
        self.assertIn("$1.00", handoff.event(str(self.profile), "quiet: x", monday)["weekly"])
        self.assertIsNone(handoff.event(str(self.profile), "quiet: x", monday + datetime.timedelta(days=1))["weekly"])

    def serve(self):
        srv = http.server.HTTPServer(("127.0.0.1", 0), Catch)
        threading.Thread(target=srv.handle_request, daemon=True).start()
        return f"http://127.0.0.1:{srv.server_port}/hook"

    def test_a_signed_post_reaches_the_webhook(self):
        ev = handoff.event(str(self.profile), "quiet: nothing fired")
        out = handoff.send(ev, {"DUALTRACK_WEBHOOK_URL": self.serve(), "DUALTRACK_WEBHOOK_SECRET": "s3"})
        self.assertEqual(out, "sent: 200")
        headers, body = Catch.got[0]
        want = "sha256=" + hmac.new(b"s3", body, hashlib.sha256).hexdigest()
        self.assertEqual(headers["X-Dualtrack-Signature"], want)
        self.assertEqual(json.loads(body)["outcome"], "quiet: nothing fired")

    def test_a_post_holding_the_canary_is_never_sent(self):
        ev = handoff.event(str(self.profile), "held: ghp_canary123 leaked")
        out = handoff.send(ev, {"DUALTRACK_WEBHOOK_URL": self.serve(), "DUALTRACK_CANARY": "ghp_canary123"})
        self.assertIn("canary", out); self.assertEqual(Catch.got, [])

    def test_a_plain_http_webhook_is_refused(self):
        self.assertIn("https", handoff.send({"a": 1}, {"DUALTRACK_WEBHOOK_URL": "http://example.invalid/hook"}))
        self.assertIn("https", handoff.send({"a": 1}, {"DUALTRACK_WEBHOOK_URL": "http://127.0.0.1.example.invalid/hook"}))

    def test_a_post_holding_a_secret_is_never_sent(self):
        ev = handoff.event(str(self.profile), "stopped: npm ERR! //registry.npmjs.org/:_authToken=npm_" + "a1" * 18)
        self.assertIn("a secret", handoff.send(ev, {"DUALTRACK_WEBHOOK_URL": self.serve()})); self.assertEqual(Catch.got, [])

    def test_a_secret_split_by_a_zero_width_character_is_never_sent(self):
        tok = "npm_" + "a1" * 18
        ev = handoff.event(str(self.profile), "stopped: //registry.npmjs.org/:_authToken=" + tok[:6] + "\u200b" + tok[6:])
        self.assertIn("a secret", handoff.send(ev, {"DUALTRACK_WEBHOOK_URL": self.serve()})); self.assertEqual(Catch.got, [])


if __name__ == "__main__":
    unittest.main()
