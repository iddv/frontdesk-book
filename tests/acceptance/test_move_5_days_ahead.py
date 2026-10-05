"""Move it to 5 days ahead.

Expected: No email is sent now; the reminder is rescheduled to 24 hours before the new start.
Source: "reschedules the reminder (see Domain rules)"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_move_5_days_ahead():
    s = System().basic()
    try:
        a,_=s.book("2026-03-05","10:00"); s.move(a,"2026-03-07","10:00"); s.run_job(); assert not s.sent
        s.set_local("2026-03-04","10:00"); s.run_job(); assert not s.sent
        s.set_local("2026-03-06","10:00"); s.run_job(); assert len(s.sent)==1
    finally:
        s.close()
