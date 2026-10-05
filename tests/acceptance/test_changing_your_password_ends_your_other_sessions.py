"""Changing your password ends your other sessions.

Expected: a session opened elsewhere with the old password is signed out after the password change
Source: the security review (SECURITY.md).
"""

import os, sys, socket, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from _helpers.security_helpers import Server, Session, setup_admin, raw, PW


def test_password_change_ends_other_sessions():
    srv = Server()
    try:
        a = setup_admin(srv)
        other = Session(srv)
        other.post("/login", {"username": "admin", "password": PW})
        assert other.req("GET", "/day")[0] == 200
        new = "Another-pass-77"
        a.post("/password", {"current": PW, "password": new, "password2": new})
        st, h, _ = other.req("GET", "/day")
        assert st == 303 and h.get("Location") == "/login", "old session still works after password change (status %d)" % st
    finally:
        srv.stop()
