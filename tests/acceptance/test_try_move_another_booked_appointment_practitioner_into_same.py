"""Try to move another Booked appointment for practitioner A into that same past-day slot.

Expected: Refused (past time and/or overlap); no change saved.
Source: "two non-cancelled appointments for the same practitioner may not overlap"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_try_move_another_booked_appointment_practitioner_into_same():
    s = System().basic()
    try:
        a,_=s.book("2026-03-02","10:00"); s.set_local("2026-03-03","09:00"); s.status(a,"attended")
        b,_=s.book("2026-03-05","10:00",pat=s.p2); r=s.move(b,"2026-03-02","10:00",confirm=True)
        assert s.appt(b)["start_utc"]=="2026-03-05 10:00:00"
    finally:
        s.close()
