#!/usr/bin/env python3
"""The dashboard, live: serve it on this machine only, so its buttons record your calls instead of copying them.

  python3 <kit>/scripts/dashboard_server.py      from the root of the product repo

Opens the page in your browser, at a URL that carries a one-time launch secret (?k=...). Every load is rebuilt from the record, so it shows calls already made.
A button runs the same decide.py command you would type, and the page shows its reply. Stops after
30 minutes with no visits, or on Ctrl-C. Stdlib only.

Safety: listens on 127.0.0.1 only, on a random port. The page, and the token in it, go only to a GET that
carries the launch secret; any other local process gets 403. A call needs the token in that page, this exact
host and origin, and JSON; anything else is refused and runs nothing. It runs only the owner's calls
(a pick, try, no, answer, result, undo), with no shell. The server itself writes nothing; decide.py does.
"""
import datetime
import hmac
import http.server
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import urllib.parse
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dashboard
import decide
import loop_lib
import profile_value

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(HERE)
CALLS = ("try", "no", "answer", "result", "undo", "owner", "allow", "resume")
IDLE = 30 * 60
LOCK = threading.Lock()


def allowed(argv):
    """Only the owner's calls, as plain strings. A digit is a pick; the rest name their call."""
    if not isinstance(argv, list) or not argv or len(argv) > 5 or not all(isinstance(a, str) and len(a) < 2000 for a in argv):
        return False
    # A record line ends at any line break Python splits on (\r, U+2028 too), and a terminal obeys escape codes.
    if any(c != "\t" and unicodedata.category(c) in ("Cc", "Zl", "Zp") for a in argv for c in a):
        return False
    if "--by" in argv:  # the page signs as the profile's Owner; a name is never taken from a request
        return False
    if argv[0] == "owner":
        return len(argv) == 3 and all(a.strip() for a in argv[1:])
    if argv[0] in ("allow", "resume"):  # the page's two buttons: no title or text, so a request cannot name another bet
        return len(argv) == 1
    return loop_lib.pick(argv[0]) or argv[0] in CALLS


class Handler(http.server.BaseHTTPRequestHandler):
    token = secret = host = origin = profile = ""
    last = [time.monotonic()]
    timeout = 10  # one silent connection cannot hold the single-threaded server, or its idle shutdown

    def log_message(self, *args):  # never write requests (or the token header) anywhere
        pass

    def reply(self, code, body, kind="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        for k, v in (("Content-Type", kind + "; charset=utf-8"), ("Content-Length", str(len(data))),
                     ("Cache-Control", "no-store"), ("Referrer-Policy", "no-referrer"),
                     ("X-Frame-Options", "DENY"), ("X-Content-Type-Options", "nosniff")):
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def refuse(self, why):
        self.reply(403, json.dumps({"code": 403, "output": f"Refused: {why}. Nothing was recorded."}))

    def do_GET(self):
        if self.headers.get("Host") != self.host:  # a page on another name (DNS rebinding) gets nothing
            return self.refuse("wrong host")
        url = urllib.parse.urlsplit(self.path)
        k = urllib.parse.parse_qs(url.query).get("k", [""])[0]
        # compare bytes: compare_digest raises on non-ASCII str
        if url.path != "/" or not hmac.compare_digest(k.encode(), self.secret.encode()):
            return self.refuse("this page opens only from the link the dashboard printed")
        self.last[0] = time.monotonic()
        text = open(self.profile).read()
        page = dashboard.render(decide.context_path(self.profile), datetime.date.today().isoformat(), KIT,
                                profile_value.field(text, "Run cap") or "none", self.profile, self.token)
        self.reply(200, page, "text/html")

    def do_POST(self):
        if self.headers.get("Host") != self.host:
            return self.refuse("wrong host")
        if self.headers.get("Origin") != self.origin:
            return self.refuse("wrong origin")
        if self.path != "/call":
            return self.refuse("unknown path")
        if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
            return self.refuse("not JSON")
        if not hmac.compare_digest(self.headers.get("X-Dualtrack-Token", "").encode("utf-8", "replace"), self.token.encode()):  # bytes, as above
            return self.refuse("bad token")
        try:
            size = int(self.headers.get("Content-Length", "0"))
            argv = json.loads(self.rfile.read(size).decode()).get("argv") if 0 < size <= 8192 else None
        except (ValueError, AttributeError):
            argv = None
        if not allowed(argv):
            return self.refuse("not one of your calls")
        self.last[0] = time.monotonic()
        if not LOCK.acquire(blocking=False):
            return self.reply(409, json.dumps({"code": 409, "output": "Another call is still being recorded. Try again in a moment."}))
        try:
            r = subprocess.run([sys.executable, os.path.join(HERE, "decide.py"), *argv], capture_output=True, text=True,
                               stdin=subprocess.DEVNULL, timeout=120, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
            code, out = r.returncode, (r.stdout + r.stderr).strip()
        except subprocess.TimeoutExpired:
            code, out = 124, "The call took too long and was stopped. Check /dualtrack before trying again."
        finally:
            LOCK.release()
        self.reply(200, json.dumps({"code": code, "output": out}))


def serve(profile, open_browser=True, port=0):
    server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    port = server.server_address[1]
    Handler.token, Handler.secret, Handler.profile = secrets.token_urlsafe(32), secrets.token_urlsafe(32), profile
    Handler.host, Handler.origin = f"127.0.0.1:{port}", f"http://127.0.0.1:{port}"
    server.timeout = 30
    return server


def main():
    profile = decide.find_profile()
    if not os.path.exists(profile):
        print("No profile.md here. Run this from your product repo, after setup.")
        return 2
    server = serve(profile)
    url = f"{Handler.origin}/?k={Handler.secret}"
    print(f"dashboard: {url}  (stops after 30 minutes unused, or Ctrl-C)", flush=True)
    # Open a 0600 file that redirects, so the secret is never on a browser launcher's argv (visible in ps).
    # shortcut: the secret still sits in the browser's own address bar and history, and in this terminal line.
    # It lives in one fixed folder so the loop's sandbox can close it to branch code (daily_loop.sh, setup_check.py).
    home = os.environ.get("DUALTRACK_HOME") or os.path.join(os.path.expanduser("~"), ".dualtrack")
    folder = os.path.join(home, "dashboard"); os.makedirs(folder, mode=0o700, exist_ok=True)
    fd, hop = tempfile.mkstemp(suffix=".html", prefix="dualtrack-", dir=folder)
    with os.fdopen(fd, "w") as f:
        f.write(f'<!doctype html><meta http-equiv=refresh content="0;url={url}"><title>Dualtrack</title>')
    webbrowser.open("file://" + hop)
    try:
        while time.monotonic() - Handler.last[0] < IDLE:
            server.handle_request()
    except KeyboardInterrupt:
        pass
    server.server_close()
    os.unlink(hop)
    print("dashboard: stopped. The page now copies calls instead of recording them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
