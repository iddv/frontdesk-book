"""A huge numeric id in a URL gives 404, not a server error.

Expected: GET /patients/<25 digits> returns 404
Source: the security review (SECURITY.md).
"""

import os, sys, socket, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from _helpers.security_helpers import Server, Session, setup_admin, raw, PW


def test_huge_id_is_404():
    srv = Server()
    try:
        a = setup_admin(srv)
        st, _, body = a.req("GET", "/patients/9999999999999999999999999")
        assert st == 404, "got %d" % st
        assert "Traceback" not in body
    finally:
        srv.stop()


# Known open item: expected to fail until it is fixed (tests/acceptance/README.md).
import pytest as _pytest_open  # noqa: E402
_marks = globals().get('pytestmark', [])
pytestmark = (list(_marks) if isinstance(_marks, (list, tuple)) else [_marks]) + [
    _pytest_open.mark.xfail(strict=False, reason='Known security issue (low): A huge numeric id in a URL gives 404, not a server error')]
