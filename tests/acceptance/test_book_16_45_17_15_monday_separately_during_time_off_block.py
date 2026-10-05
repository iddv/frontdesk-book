"""Book at 16:45–17:15 on a Monday, and separately during a time-off block.

Expected: Both refused.
Source: "Whether booking outside working hours or in time-off is refused or allowed after confirmation."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_book_16_45_17_15_monday_separately_during_time_off_block():
    s = System().basic()
    try:
        s.settings(booking__outside_hours="block"); s.set_hours(s.pa,{i:"09:00-17:00" for i in range(5)})
        a,r=s.book("2026-03-09","16:45",confirm=True); assert a is None and "outside working hours" in r.text
    finally:
        s.close()
