"""Book outside working hours without confirming, then with confirming.

Expected: Without confirmation nothing is saved and a warning is returned; with confirmation it is saved as Booked.
Source: "allowed after confirmation"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_book_outside_working_hours_without_confirming_confirming():
    s = System().basic()
    try:
        s.set_hours(s.pa,{i:"09:00-17:00" for i in range(5)})
        a,r=s.book("2026-03-09","17:00"); assert a is None and "outside working hours" in r.text
        b,_=s.book("2026-03-09","17:00",confirm=True); assert b
    finally:
        s.close()
