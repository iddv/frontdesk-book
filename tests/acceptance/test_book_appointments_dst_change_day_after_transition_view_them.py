"""Book appointments on the DST-change day after the transition, and view them.

Expected: Appointments keep their entered wall-clock times on the day view and in exports; overlap checks use real time.
Source: "times are stored with that zone and handle DST changes correctly"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_book_appointments_dst_change_day_after_transition_view_them():
    s = System().basic()
    try:
        s.set_local("2026-03-28","12:00"); a,_=s.book("2026-03-29","10:00",confirm=True); b,_=s.book("2026-03-29","10:30",pat=s.p2,confirm=True)
        c,r=s.book("2026-03-29","10:15",pr=s.pa,pat=s.p2,confirm=True); assert a and b and c is None
        assert s.appt(a)["start_utc"]=="2026-03-29 09:00:00" and "10:00" in s.admin.get("/day",date="2026-03-29").text
    finally:
        s.close()
