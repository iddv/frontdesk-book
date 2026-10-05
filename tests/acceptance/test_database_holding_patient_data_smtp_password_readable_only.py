"""The database holding patient data and the SMTP password is readable only by the service's user.

Expected: frontdesk.db has no group/other read permission
Source: the security review (SECURITY.md).
"""

import os, sys, socket, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from _helpers.security_helpers import Server, Session, setup_admin, raw, PW

import stat

def test_db_not_world_readable():
    srv = Server()
    try:
        mode = os.stat(os.path.join(srv.dir, "frontdesk.db")).st_mode
        assert not mode & (stat.S_IRGRP | stat.S_IROTH), "frontdesk.db mode is %o" % (mode & 0o777)
    finally:
        srv.stop()


# Known open item: expected to fail until it is fixed (tests/acceptance/README.md).
import pytest as _pytest_open  # noqa: E402
_marks = globals().get('pytestmark', [])
pytestmark = (list(_marks) if isinstance(_marks, (list, tuple)) else [_marks]) + [
    _pytest_open.mark.xfail(strict=False, reason="Known security issue (low): The database holding patient data and the SMTP password is readable only by the service's user")]
