"""A receptionist cannot use admin actions, even with a valid CSRF token.

Expected: 403 on admin pages and on POST /admin/staff and /admin/settings
Source: the security review (SECURITY.md).
"""

import os, sys, socket, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from _helpers.security_helpers import Server, Session, setup_admin, raw, PW


def test_receptionist_blocked_from_admin():
    srv = Server()
    try:
        a = setup_admin(srv)
        a.post("/admin/staff", {"username": "rita", "role": "receptionist", "password": PW, "password2": PW})
        r = Session(srv)
        r.post("/login", {"username": "rita", "password": PW})
        n = "Rita-new-pass-1"
        r.post("/password", {"current": PW, "password": n, "password2": n})
        assert r.req("GET", "/day")[0] == 200
        for p in ("/admin/staff", "/admin/backup/download", "/admin/settings"):
            assert r.req("GET", p)[0] == 403, p
        assert r.post("/admin/staff", {"username": "evil", "role": "admin", "password": PW, "password2": PW}, csrf_from="/day")[0] == 403
        assert r.post("/admin/settings", {"booking.outside_hours": "block"}, csrf_from="/day")[0] == 403
    finally:
        srv.stop()
