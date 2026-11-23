"""A credential sent to one host never follows a redirect to another (directory review R05, R07)."""
import http.server
import pathlib
import sys
import threading
import unittest

KIT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "scripts"))
import app_token
import handoff


def serve(handler):
    s = http.server.HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


class Redirects(unittest.TestCase):
    def setUp(self):
        self.seen = seen = []

        class Other(http.server.BaseHTTPRequestHandler):  # a different host: localhost, not 127.0.0.1
            def do_GET(self):
                seen.append(dict(self.headers)); self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
            do_POST = do_GET
            def log_message(self, *a): pass
        self.other = serve(Other)
        to = f"http://localhost:{self.other.server_port}/x"

        class Bounce(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                n = int(self.headers.get("Content-Length") or 0); self.rfile.read(n)
                self.send_response(302); self.send_header("Location", to); self.send_header("Content-Length", "0"); self.end_headers()
            do_POST = do_GET
            def log_message(self, *a): pass
        self.bounce = serve(Bounce)
        self.url = f"http://127.0.0.1:{self.bounce.server_port}"

    def tearDown(self):
        for s in (self.other, self.bounce):
            s.shutdown(); s.server_close()

    def test_the_app_token_call_does_not_carry_its_bearer_to_another_host(self):
        with self.assertRaises(Exception):
            app_token.call(self.url + "/repos/o/r/installation", "signed-jwt")
        self.assertEqual(self.seen, [])

    def test_a_webhook_redirect_is_not_followed_and_is_reported(self):
        env = {"DUALTRACK_WEBHOOK_URL": self.url + "/hook", "DUALTRACK_WEBHOOK_SECRET": "s"}
        self.assertEqual(handoff.send({"run": "x"}, env), "not delivered: the receiver answered HTTP 302")
        self.assertEqual(self.seen, [])


if __name__ == "__main__":
    unittest.main()
