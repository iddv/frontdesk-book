"""Start the service.

Expected: Both are marked Skipped (too late); no email sent.
Source: "otherwise it marks it Skipped (too late)"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_start_service_2():
    s = System().basic()
    try:
        a,_=s.book("2026-03-05","10:00"); b,_=s.book("2026-03-05","08:00",pat=s.p2); s.set_local("2026-03-05","09:10"); s.restart()
        assert not s.sent and s.reminder(a)["reason"]=="too late" and s.reminder(b)["reason"]=="too late"
    finally:
        s.close()
