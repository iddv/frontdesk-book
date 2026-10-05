"""Save Monday 09:00–12:00 and 11:00–15:00; save 14:00–10:00; save 09:00–12:00 and 12:00–17:00.

Expected: Overlapping and reversed ranges are rejected with a reason; the touching ranges are accepted.
Source: "Overlapping hour ranges on one day, or end time before start time: the range is rejected with the reason."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_save_monday_09_00_12_00_11_00_15_00_save_14_00_10_00_save_09():
    s = System().basic()
    try:
        s.set_hours(s.pa,{0:"09:00-12:00, 11:00-15:00"}); assert D.hours_for(s.conn,s.pa)[0]==[(480,1080)]
        s.set_hours(s.pa,{0:"14:00-10:00"}); assert D.hours_for(s.conn,s.pa)[0]==[(480,1080)]
        s.set_hours(s.pa,{0:"09:00-12:00, 12:00-17:00"}); assert D.hours_for(s.conn,s.pa)[0]==[(540,720),(720,1020)]
    finally:
        s.close()
