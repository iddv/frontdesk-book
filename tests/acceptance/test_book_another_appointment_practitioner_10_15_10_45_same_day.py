"""Book another appointment for practitioner A at 10:15–10:45 the same day.

Expected: Refused with a conflict message naming the existing patient and 10:00–10:30; nothing is saved.
Source: "two non-cancelled appointments for the same practitioner may not overlap"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_book_another_appointment_practitioner_10_15_10_45_same_day():
    s = System().basic()
    try:
        a,_=s.book(D1,"10:00"); b,r=s.book(D1,"10:15",pat=s.p2)
        assert b is None and "Conflicts with Ann Lee 10:00–10:30" in r.text
    finally:
        s.close()
