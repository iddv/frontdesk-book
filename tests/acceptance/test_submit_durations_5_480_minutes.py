"""Submit durations of 5 and 480 minutes.

Expected: Both accepted.
Source: "Durations run from 5 to 480 minutes."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_submit_durations_5_480_minutes():
    s = System().basic()
    try:
        a,_=s.book(D1,"09:00",dur=5); b,_=s.book("2026-03-05","08:00",dur=480,pat=s.p2); assert a and b
    finally:
        s.close()
