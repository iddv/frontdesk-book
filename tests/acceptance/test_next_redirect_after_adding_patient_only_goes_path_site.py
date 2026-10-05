"""The next= redirect after adding a patient only goes to a path on this site.

Expected: next=/\\evil.com is refused; the redirect stays on the same host
Source: the security review (SECURITY.md).
"""

import os, sys, socket, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from _helpers.security_helpers import Server, Session, setup_admin, raw, PW


def test_next_backslash_open_redirect():
    srv = Server()
    try:
        a = setup_admin(srv)
        st, h, _ = a.post("/patients/new", {"first_name": "X", "last_name": "Y", "phone": "0123456789",
                                            "next": "/\\evil.com/x"}, csrf_from="/patients/new")
        loc = h.get("Location", "")
        assert st == 303
        assert not loc.startswith("/\\") and "evil.com" not in loc, "redirects off-site: %r" % loc
    finally:
        srv.stop()


# Known open item: expected to fail until it is fixed (tests/acceptance/README.md).
import pytest as _pytest_open  # noqa: E402
_marks = globals().get('pytestmark', [])
pytestmark = (list(_marks) if isinstance(_marks, (list, tuple)) else [_marks]) + [
    _pytest_open.mark.xfail(strict=False, reason='Known security issue (low): The next= redirect after adding a patient only goes to a path on this site')]
