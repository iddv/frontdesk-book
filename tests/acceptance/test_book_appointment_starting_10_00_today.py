"""Book an appointment starting 10:00 today.

Expected: Allowed, since 10:00 is the current time rounded down to the 5-minute grid.
Source: "a new booking or move may not start before the current time rounded down to the 5-minute grid"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_book_appointment_starting_10_00_today():
    s = System().basic()
    try:
        s.set_local("2026-03-02","10:03"); a,r=s.book("2026-03-02","10:00"); assert a
    finally:
        s.close()
