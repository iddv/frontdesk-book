"""Book an appointment starting in 1 hour 55 minutes, and another starting in exactly 2 hours.

Expected: Both reminders are Skipped (too late); no email is sent.
Source: "provided the start is more than 2 hours away (default); otherwise it is Skipped (too late)"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_book_appointment_starting_1_hour_55_minutes_another_starting():
    s = System().basic()
    try:
        a,_=s.book("2026-03-02","09:55"); b,_=s.book("2026-03-02","10:00",pr=s.pb,pat=s.p2); s.run_job()
        assert not s.sent and s.reminder(a)["reason"]=="too late" and s.reminder(b)["reason"]=="too late"
    finally:
        s.close()
