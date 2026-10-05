"""Submit a start time not on the 5-minute grid (e.g. 10:02).

Expected: Refused with a clear field error; nothing saved.
Source: "The time grid uses 5-minute steps (default)."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_submit_start_time_not_5_minute_grid_e_g_10_02():
    s = System().basic()
    try:
        a,r=s.book(D1,"10:02"); assert a is None and "grid" in r.text
    finally:
        s.close()
