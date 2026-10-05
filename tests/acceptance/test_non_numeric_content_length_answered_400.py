"""A non-numeric Content-Length is answered with 400.

Expected: the server replies 400 Bad Request instead of dropping the connection with a logged traceback
Source: the security review (SECURITY.md).
"""

import os, sys, socket, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from _helpers.security_helpers import Server, Session, setup_admin, raw, PW


def test_invalid_content_length_400():
    srv = Server()
    try:
        out = raw(srv.port, b"POST /login HTTP/1.1\r\nHost: x\r\nContent-Length: abc\r\n\r\n", 5)
        assert out.startswith(b"HTTP/1.") and b" 400 " in out.split(b"\r\n")[0], "reply: %r" % out[:60]
    finally:
        srv.stop()
