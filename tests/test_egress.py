"""egress_proxy.py on any platform: allowed hosts pass, others get 403 and are logged. No internet needed."""
import http.server
import pathlib
import socket
import subprocess
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
try:
    import scratch
except ImportError:  # run as tests.test_x from the repo root
    from tests import scratch

KIT = pathlib.Path(__file__).resolve().parent.parent


class Egress(unittest.TestCase):
    def setUp(self):
        self.d = pathlib.Path(scratch.mkdtemp())
        self.site = http.server.HTTPServer(("127.0.0.1", 0), type("H", (http.server.BaseHTTPRequestHandler,), {
            "do_GET": lambda s: (s.send_response(200), s.end_headers(), s.wfile.write(b"ok")),
            "log_message": lambda *a: None}))
        threading.Thread(target=self.site.serve_forever, daemon=True).start()
        self.addCleanup(self.site.shutdown)

    def proxy(self, domains):
        p = subprocess.Popen([sys.executable, str(KIT / "scripts/egress_proxy.py"), str(self.d / "port"), str(self.d / "log"), domains])
        self.addCleanup(p.terminate)
        for _ in range(50):
            if (self.d / "port").exists() and (self.d / "port").read_text():
                break
            time.sleep(0.1)
        px = f"http://127.0.0.1:{(self.d / 'port').read_text()}"
        return urllib.request.build_opener(urllib.request.ProxyHandler({"http": px, "https": px}))

    def test_an_allowed_host_passes(self):
        body = self.proxy(f"127.0.0.1:{self.site.server_port}").open(f"http://127.0.0.1:{self.site.server_port}/", timeout=5).read()
        self.assertEqual(body, b"ok")
        self.assertIn("allowed 127.0.0.1", (self.d / "log").read_text())

    def test_a_host_not_allowed_is_refused_and_logged(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.proxy("pypi.org").open(f"http://127.0.0.1:{self.site.server_port}/", timeout=5)
        self.assertEqual(e.exception.code, 403)
        self.assertIn("blocked 127.0.0.1", (self.d / "log").read_text())

    def test_the_bridge_carries_a_request_to_the_proxys_unix_socket_and_the_rules_still_hold(self):
        sock = pathlib.Path(scratch.mkdtemp(dir="/tmp")) / "egress.sock"  # short: a Unix socket path holds about 100 characters
        p = subprocess.Popen([sys.executable, str(KIT / "scripts/egress_proxy.py"), str(self.d / "port"), str(self.d / "log"),
                              f"127.0.0.1:{self.site.server_port}", str(sock)])
        self.addCleanup(p.terminate)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
        b = subprocess.Popen([sys.executable, str(KIT / "scripts/egress_bridge.py"), str(sock), str(port)])
        self.addCleanup(b.terminate)
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close(); break
            except OSError:
                time.sleep(0.1)
        px = f"http://127.0.0.1:{port}"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": px}))
        self.assertEqual(opener.open(f"http://127.0.0.1:{self.site.server_port}/", timeout=5).read(), b"ok")
        with self.assertRaises(urllib.error.HTTPError) as e:
            opener.open("http://not-allowed.invalid/", timeout=5)
        self.assertEqual(e.exception.code, 403)

    def test_subdomains_match_and_lookalikes_do_not(self):
        sys.path.insert(0, str(KIT / "scripts"))
        import egress_proxy
        self.assertTrue(egress_proxy.allowed("files.pypi.org", ["pypi.org"]))
        self.assertFalse(egress_proxy.allowed("evilpypi.org", ["pypi.org"]))
        self.assertFalse(egress_proxy.allowed("pypi.org.evil.com", ["pypi.org"]))

    def test_only_ports_80_and_443_unless_the_entry_names_one(self):
        sys.path.insert(0, str(KIT / "scripts"))
        import egress_proxy
        self.assertTrue(egress_proxy.allowed("pypi.org", ["pypi.org"], 443))
        self.assertTrue(egress_proxy.allowed("pypi.org", ["pypi.org"], 80))
        self.assertFalse(egress_proxy.allowed("pypi.org", ["pypi.org"], 22))
        self.assertFalse(egress_proxy.allowed("files.pypi.org", ["pypi.org"], 6379))
        self.assertTrue(egress_proxy.allowed("pypi.org", ["pypi.org:8080"], 8080))
        self.assertFalse(egress_proxy.allowed("pypi.org", ["pypi.org:8080"], 443))

    def test_a_shared_hosting_apex_admits_only_itself(self):
        sys.path.insert(0, str(KIT / "scripts"))
        import egress_proxy
        for apex in egress_proxy.SHARED_APEXES:
            self.assertTrue(egress_proxy.allowed(apex, [apex]), apex)
            self.assertFalse(egress_proxy.allowed("tenant." + apex, [apex]), apex)
        self.assertTrue(egress_proxy.allowed("me.github.io", ["me.github.io"]))

    def test_a_star_pattern_matches_a_preview_host_and_no_other_tenant(self):
        sys.path.insert(0, str(KIT / "scripts"))
        import egress_proxy
        a = egress_proxy.allowed
        self.assertTrue(a("myapp-git-x-team.vercel.app", ["myapp-*.vercel.app"]))
        self.assertTrue(a("myapp-git-x-team.vercel.app", ["myapp-*-team.vercel.app"]))
        self.assertTrue(a("myapp-1.vercel.app:8080".split(":")[0], ["myapp-*.vercel.app:8080"], 8080))
        self.assertFalse(a("myapp-1.vercel.app", ["myapp-*.vercel.app:8080"], 443))
        self.assertFalse(a("other-git-x.vercel.app", ["myapp-*.vercel.app"]))
        self.assertFalse(a("myapp-a.b.vercel.app", ["myapp-*.vercel.app"]))
        self.assertFalse(a("myapp-.vercel.app", ["myapp-*.vercel.app"]))
        for bad in ["*.vercel.app", "*-x.vercel.app", "a*b*.vercel.app", "myapp.*.vercel.app"]:
            self.assertFalse(a("tenant-x.vercel.app", [bad]), bad)
        self.assertTrue(a("anything.example", ["*"]))

    def test_private_loopback_and_metadata_addresses_are_refused_unless_named_exactly(self):
        sys.path.insert(0, str(KIT / "scripts"))
        import egress_proxy
        for ip in ["127.0.0.1", "10.0.0.5", "192.168.1.1", "172.16.0.1", "169.254.169.254", "::1", "fe80::1",
                   "::ffff:10.0.0.1", "0.0.0.0", "100.64.0.1", "224.0.0.1"]:
            self.assertIsNone(egress_proxy.public_address(ip, 80), ip)
        self.assertEqual(egress_proxy.public_address("8.8.8.8", 443), "8.8.8.8")
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.proxy("*").open(f"http://127.0.0.1:{self.site.server_port}/", timeout=5)
        self.assertEqual(e.exception.code, 403)
        self.assertIn("blocked 127.0.0.1", (self.d / "log").read_text())

    def test_a_name_that_answers_differently_the_second_time_is_connected_once_to_the_first_answer(self):
        sys.path.insert(0, str(KIT / "scripts"))
        import egress_proxy
        from unittest import mock
        lookups, connects = [], []

        def resolver(host, port, *a, **k):  # public first, loopback on any later lookup
            lookups.append(host)
            ip = "8.8.8.8" if len(lookups) == 1 else "127.0.0.1"
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

        def connect(addr, *a, **k):
            connects.append(addr[0])
            raise OSError("no real connection in a test")

        with mock.patch.object(socket, "getaddrinfo", resolver), mock.patch.object(socket, "create_connection", connect):
            srv = egress_proxy.Proxy(("127.0.0.1", 0), egress_proxy.handler(["example"], str(self.d / "log")))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            self.addCleanup(srv.server_close)
            self.addCleanup(srv.shutdown)
            with socket.socket() as c:
                c.settimeout(5)
                c.connect(srv.server_address)
                c.sendall(b"CONNECT rebind.example:443 HTTP/1.1\r\n\r\n")
                c.recv(1024)
        self.assertEqual(connects, ["8.8.8.8"])  # the first answer, never the host name (a name is looked up again) or 127.0.0.1

    def test_a_star_entry_opens_the_proxy_only_in_learn_mode(self):
        sys.path.insert(0, str(KIT / "scripts"))
        import egress_proxy
        self.assertEqual(egress_proxy.parse_domains("*, pypi.org"), ["pypi.org"])
        self.assertFalse(egress_proxy.allowed("anything.example", egress_proxy.parse_domains("*")))
        self.assertTrue(egress_proxy.allowed("pypi.org", egress_proxy.parse_domains("*, pypi.org")))
        self.assertEqual(egress_proxy.parse_domains("*, pypi.org", learn=True), ["*", "pypi.org"])
        self.assertTrue(egress_proxy.allowed("anything.example", egress_proxy.parse_domains("*", learn=True)))

    def test_setup_starts_its_proxy_in_learn_mode_and_nothing_else_passes_the_flag(self):
        sys.path.insert(0, str(KIT / "scripts"))
        import setup_check
        from unittest import mock
        with mock.patch.object(setup_check.subprocess, "Popen") as popen, \
                mock.patch.object(setup_check.os.path, "exists", return_value=True), \
                mock.patch("builtins.open", mock.mock_open(read_data="1234")):
            setup_check.watch_proxy()
        self.assertIn("--learn", popen.call_args[0][0])
        loop = (KIT / "scripts/daily_loop.sh").read_text()
        self.assertNotIn("--learn", loop)

    def test_the_log_names_the_port(self):
        with self.assertRaises(urllib.error.HTTPError):
            self.proxy("pypi.org").open(f"http://127.0.0.1:{self.site.server_port}/", timeout=5)
        self.assertIn(f"blocked 127.0.0.1 {self.site.server_port}", (self.d / "log").read_text())


if __name__ == "__main__":
    unittest.main()
