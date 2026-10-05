"""Cancel it.

Expected: It is Cancelled and flagged late.
Source: "a cancellation made less than 24 hours before the start"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_cancel():
    s = System().basic()
    try:
        a,_=s.book("2026-03-03","07:55",confirm=True); s.cancel(a); assert s.appt(a)["late_cancel"]==1
    finally:
        s.close()
