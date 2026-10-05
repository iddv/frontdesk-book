"""Move it to a new time 3 days ahead.

Expected: A new reminder with subject 'Your appointment has changed' is sent 24 hours before the new time (or immediately if inside the window and over 2 hours away).
Source: "When an appointment with a Sent reminder is moved, a new reminder is sent for the new time by the same rules, with the subject "Your appointment has changed"."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_move_new_time_3_days_ahead():
    s = System().basic()
    try:
        a,_=s.book("2026-03-02","15:00"); s.run_job(); assert s.reminder(a)["state"]=="sent"
        s.move(a,"2026-03-05","10:00"); s.run_job(); assert len(s.sent)==1
        s.set_local("2026-03-04","10:00"); s.run_job(); assert len(s.sent)==2 and s.sent[1]["subject"]=="Your appointment has changed"
    finally:
        s.close()
