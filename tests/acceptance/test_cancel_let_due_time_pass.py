"""Cancel it and let the due time pass.

Expected: No reminder is sent; state shows Not needed.
Source: "stops any pending reminder"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_cancel_let_due_time_pass():
    s = System().basic()
    try:
        a,_=s.book("2026-03-05","10:00"); s.cancel(a); s.set_local("2026-03-04","10:00"); s.run_job()
        assert not [m for m in s.sent if "reminder" in m["subject"].lower()] and s.reminder(a)["state"]=="not_needed"
    finally:
        s.close()
