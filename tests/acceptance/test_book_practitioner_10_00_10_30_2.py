"""Book practitioner A at 10:00–10:30.

Expected: Booking succeeds; the cancelled appointment remains on record as Cancelled.
Source: "Cancelled appointments never block."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_book_practitioner_10_00_10_30_2():
    s = System().basic()
    try:
        a,_=s.book(D1,"10:00"); s.cancel(a); b,r=s.book(D1,"10:00",pat=s.p2); assert b
    finally:
        s.close()
