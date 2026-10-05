"""Book an appointment starting in 5 hours.

Expected: The reminder is sent immediately (within the next job run) and shows Sent.
Source: "If booked or moved inside that window, it is sent immediately, provided the start is more than 2 hours away"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_book_appointment_starting_5_hours():
    s = System().basic()
    try:
        a,_=s.book("2026-03-02","13:00"); s.run_job(); assert len(s.sent)==1 and s.reminder(a)["state"]=="sent"
    finally:
        s.close()
