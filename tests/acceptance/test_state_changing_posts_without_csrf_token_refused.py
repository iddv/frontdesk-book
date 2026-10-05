"""State-changing POSTs without the CSRF token are refused.

Expected: 400 for a signed-in POST missing _csrf, even with a foreign Origin
Source: the security review (SECURITY.md).
"""

import os, sys, socket, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from _helpers.security_helpers import Server, Session, setup_admin, raw, PW


def test_csrf_required():
    srv = Server()
    try:
        a = setup_admin(srv)
        assert a.req("POST", "/admin/settings", {"booking.outside_hours": "block"}, headers={"Origin": "http://evil.example"})[0] == 400
    finally:
        srv.stop()
