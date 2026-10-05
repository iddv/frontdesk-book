"""Book practitioner A at 09:30–10:05.

Expected: Refused as a conflict (a 5-minute overlap still counts).
Source: "two non-cancelled appointments for the same practitioner may not overlap"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_book_practitioner_09_30_10_05():
    s = System().basic()
    try:
        a,_=s.book(D1,"10:00"); b,r=s.book(D1,"09:30",dur=35,pat=s.p2); assert b is None and "Conflicts with" in r.text
    finally:
        s.close()
