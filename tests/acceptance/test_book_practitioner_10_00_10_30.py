"""Book practitioner A at 10:00–10:30.

Expected: Booking succeeds; back-to-back appointments are not a conflict.
Source: "An appointment ending at 10:00 and one starting at 10:00 do not overlap."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_book_practitioner_10_00_10_30():
    s = System().basic()
    try:
        a,_=s.book(D1,"09:30"); b,r=s.book(D1,"10:00",pat=s.p2); assert b
    finally:
        s.close()
