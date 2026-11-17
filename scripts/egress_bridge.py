#!/usr/bin/env python3
"""Linux only: inside the tests' sandbox, which has no network at all, listen on 127.0.0.1:<port> and hand every
connection to the egress proxy's Unix socket. Code that ignores the proxy setting finds nothing to connect to.

  egress_bridge.py <unix_socket> <port>
"""
import os
import socket
import socketserver
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from egress_proxy import pipe  # noqa: E402


class Bridge(socketserver.ThreadingTCPServer):
    daemon_threads = allow_reuse_address = True


class Hop(socketserver.BaseRequestHandler):
    def handle(self):
        up = socket.socket(socket.AF_UNIX)
        up.connect(sys.argv[1])
        pipe(self.request, up)


if __name__ == "__main__":
    Bridge(("127.0.0.1", int(sys.argv[2])), Hop).serve_forever()
