"""Idle connections are closed by the server and do not block the service.

Opens 50 connections that send nothing, waits 40 seconds, and expects the server to have closed
every one of them (quietly, or after a 408 answer) and /health to still answer 200.
Source: SECURITY.md (slowloris, not checked) and the request handler's missing socket timeout.
"""

import os, sys, socket, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from _helpers.security_helpers import Server, raw


def test_idle_connections_are_closed_and_health_answers():
    srv = Server()
    socks = []
    try:
        for _ in range(50):
            socks.append(socket.create_connection(("127.0.0.1", srv.port), 10))
        time.sleep(40)
        still_open = 0
        for s in socks:
            s.settimeout(2)
            try:
                while s.recv(4096):
                    pass  # an answer such as 408 is fine; wait for the close
            except socket.timeout:
                still_open += 1
            except OSError:
                pass  # reset by the server: closed
        assert still_open == 0, "%d of 50 idle connections were still open after 40 seconds" % still_open
        out = raw(srv.port, b"GET /health HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
        assert out.startswith(b"HTTP/1.0 200") or out.startswith(b"HTTP/1.1 200"), out[:80]
    finally:
        for s in socks:
            s.close()
        srv.stop()
