"""Book 16:30–17:00.

Expected: Accepted: ending exactly at the end of working hours is inside hours.
Source: "Outside working hours or in time-off: blocked"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_book_16_30_17_00():
    s = System().basic()
    try:
        s.settings(booking__outside_hours="block"); s.set_hours(s.pa,{i:"09:00-17:00" for i in range(5)})
        a,r=s.book("2026-03-09","16:30"); assert a
    finally:
        s.close()
