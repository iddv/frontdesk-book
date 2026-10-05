"""Book practitioner A at 10:00–10:30 for a different patient.

Expected: Booking succeeds; overlap is only checked per practitioner.
Source: "two non-cancelled appointments for the same practitioner may not overlap"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_book_practitioner_10_00_10_30_different_patient():
    s = System().basic()
    try:
        a,_=s.book(D1,"10:00",pr=s.pb); b,r=s.book(D1,"10:00",pat=s.p2); assert b
    finally:
        s.close()
