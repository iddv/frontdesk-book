"""Book or move an appointment to start at 09:55 today, or any time on a past date.

Expected: Refused as in the past; nothing saved.
Source: "a new booking or move may not start before the current time rounded down to the 5-minute grid. Today's earlier slots are closed."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_book_move_appointment_start_09_55_today_any_time_past_date():
    s = System().basic()
    try:
        s.set_local("2026-03-02","10:03"); a,r=s.book("2026-03-02","09:55"); assert a is None and "past" in r.text
        b,_=s.book(D1,"10:00"); s.move(b,"2026-03-01","10:00"); assert s.appt(b)["start_utc"]=="2026-03-04 10:00:00"
    finally:
        s.close()
