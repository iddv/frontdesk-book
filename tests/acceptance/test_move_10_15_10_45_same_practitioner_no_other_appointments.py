"""Move it to 10:15–10:45 for the same practitioner, with no other appointments.

Expected: Accepted; the appointment does not conflict with its own old time.
Source: "two non-cancelled appointments for the same practitioner may not overlap."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_move_10_15_10_45_same_practitioner_no_other_appointments():
    s = System().basic()
    try:
        a,_=s.book(D1,"10:00"); s.move(a,D1,"10:15"); assert s.appt(a)["start_utc"]=="2026-03-04 10:15:00"
    finally:
        s.close()
