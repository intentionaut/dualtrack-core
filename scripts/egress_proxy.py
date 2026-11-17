#!/usr/bin/env python3
"""A local proxy that lets tests reach only the profile's Allowed domains. Standard library only.

  egress_proxy.py [--learn] <port_file> <log_file> <domains|*> [unix_socket]

It listens on 127.0.0.1 on a free port and writes that port to <port_file>. Each host asked for is logged once
to <log_file> as "allowed <host>" or "blocked <host>". "*" allows every host and only records them: setup uses it, with --learn, to
learn which domains the tests call. Without --learn a "*" entry is dropped, so a profile cannot open the proxy. The tests' sandbox reaches only localhost, so code that skips the proxy fails
closed rather than getting out. On Linux the sandbox has no network at all, so the proxy also listens on
<unix_socket>, which a bridge inside the sandbox (egress_bridge.py) reaches.
"""
import ipaddress
import re
import select
import socket
import socketserver
import sys
import threading
import urllib.parse


# Multi-tenant hosts: a bare entry would admit every tenant's subdomain, so it matches only the exact host.
SHARED_APEXES = {"github.io", "s3.amazonaws.com", "herokuapp.com", "vercel.app", "netlify.app", "pages.dev",
                 "workers.dev", "azurewebsites.net", "cloudfront.net", "appspot.com"}


def pattern_matches(host, d):
    """`d` holds one `*` in its leftmost label: one or more of [a-z0-9-], never a dot. Anything else matches nothing."""
    first, _, rest = d.partition(".")
    if d.count("*") != 1 or "*" not in first or not rest:
        return False
    if first.startswith("*") and rest in SHARED_APEXES:  # the owner's fixed prefix keeps other tenants out
        return False
    return re.fullmatch(re.escape(first).replace(r"\*", "[a-z0-9-]+") + "." + re.escape(rest), host) is not None


def allowed(host, domains, port=443):
    """An entry is `host` (ports 80 and 443 only) or `host:port` (that port only); the host may hold a `*`."""
    host = host.lower().rstrip(".")
    if "*" in domains:
        return True
    for d in domains:
        d, _, p = d.partition(":") if d.rpartition(":")[2].isdigit() else (d, "", "")
        if (int(p) != port) if p else (port not in (80, 443)):
            continue
        if host == d or ("*" in d and pattern_matches(host, d)) or (d not in SHARED_APEXES and host.endswith("." + d)):
            return True
    return False


def public_address(host, port):
    """The first address `host` resolves to, only if every address is public: a name that points at this machine,
    the local network, a cloud metadata address (169.254.169.254) or anything not globally routable is refused.
    The proxy connects to that address, so a second lookup cannot swap in a private one."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        return None
    addrs = []
    for *_, sa in infos:
        ip = ipaddress.ip_address(sa[0].split("%")[0])
        ip = getattr(ip, "ipv4_mapped", None) or ip
        if not ip.is_global or ip.is_multicast:
            return None
        addrs.append(sa[0])
    return addrs[0] if addrs else None


class Proxy(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True


class UnixProxy(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True


def handler(domains, log_file):
    seen, lock = set(), threading.Lock()

    def note(verdict, host, port):
        with lock:
            if (verdict, host, port) not in seen:
                seen.add((verdict, host, port))
                with open(log_file, "a") as f:
                    f.write(f"{verdict} {host} {port}\n")

    class Handle(socketserver.StreamRequestHandler):
        def handle(self):
            line = self.rfile.readline(65536).decode("latin-1")
            parts = line.split()
            if len(parts) != 3:
                return
            method, target, version = parts
            headers = []
            while True:
                h = self.rfile.readline(65536)
                if h in (b"\r\n", b"\n", b""):
                    break
                headers.append(h)
            if method == "CONNECT":
                host, _, port = target.rpartition(":")
                rest = b""
            else:
                u = urllib.parse.urlsplit(target)
                host, port = u.hostname or "", u.port or 80
                path = u.path or "/"
                if u.query:
                    path += "?" + u.query
                rest = f"{method} {path} {version}\r\n".encode("latin-1") + b"".join(
                    h for h in headers if not h.lower().startswith(b"proxy-")) + b"\r\n"
            host = host.strip("[]")
            try:
                port = int(port)
            except ValueError:
                port = 0
            if not host or not allowed(host, domains, port):
                note("blocked", host or "?", port)
                self.wfile.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                return
            # A private address passes only when an Allowed entry names that exact host (a staging box on the owner's network).
            named = any(d.lower() in (host.lower(), f"{host.lower()}:{port}") for d in domains if d != "*")
            addr = public_address(host, port) or (named and host)
            if not addr:
                note("blocked", host, port)
                self.wfile.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                return
            note("allowed", host, port)
            try:
                up = socket.create_connection((addr, port), timeout=30)
            except OSError:
                self.wfile.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
                return
            if method == "CONNECT":
                self.wfile.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
            else:
                up.sendall(rest)
            self.wfile.flush()
            pipe(self.connection, up)

    return Handle


def pipe(a, b):
    try:
        while True:
            r, _, _ = select.select([a, b], [], [], 60)
            if not r:
                return
            for s in r:
                data = s.recv(65536)
                if not data:
                    return
                (b if s is a else a).sendall(data)
    except OSError:
        return
    finally:
        b.close()


def parse_domains(spec, learn=False):
    domains = [d.strip().lower().lstrip("*.").rstrip(".") if d.strip() != "*" else "*"
               for d in spec.split(",") if d.strip() and "<" not in d and d.strip().lower() != "none"]
    return domains if learn else [d for d in domains if d != "*"]


def main(argv):
    learn = "--learn" in argv
    port_file, log_file, spec, *unix = [a for a in argv if a != "--learn"]
    domains = parse_domains(spec, learn)
    handle = handler(domains, log_file)
    if unix:
        threading.Thread(target=UnixProxy(unix[0], handle).serve_forever, daemon=True).start()
    server = Proxy(("127.0.0.1", 0), handle)
    with open(port_file, "w") as f:
        f.write(str(server.server_address[1]))
    server.serve_forever()


if __name__ == "__main__":
    main(sys.argv[1:])
