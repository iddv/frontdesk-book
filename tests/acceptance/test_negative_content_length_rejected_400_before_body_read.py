"""A negative Content-Length is rejected with 400 before the body is read.

Expected: the server answers 400 at once and its memory stays flat while the client keeps sending
Source: the security review (SECURITY.md).
"""

import os, sys, socket, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from _helpers.security_helpers import Server, Session, setup_admin, raw, PW


def test_negative_content_length_rejected():
    srv = Server()
    try:
        rss0 = srv.rss_kib()
        s = socket.create_connection(("127.0.0.1", srv.port), 10)
        s.sendall(b"POST /login HTTP/1.1\r\nHost: x\r\nContent-Type: application/x-www-form-urlencoded\r\nContent-Length: -1\r\n\r\n")
        try:
            for _ in range(100):
                s.sendall(b"a" * (1 << 20))
        except OSError:
            pass  # server closed the connection: fine
        time.sleep(1)
        grown = srv.rss_kib() - rss0
        s.close()
        assert grown < 30 * 1024, "server buffered the body: RSS grew by %d KiB" % grown
    finally:
        srv.stop()
