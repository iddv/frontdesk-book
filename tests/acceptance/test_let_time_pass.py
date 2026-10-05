"""Let time pass.

Expected: Reminder state is Pending with due time 24 hours before start; exactly one reminder is sent at that time and state becomes Sent.
Source: "one reminder per appointment, sent 24 hours before the start"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_let_time_pass():
    s = System().basic()
    try:
        a,_=s.book("2026-03-05","10:00"); assert s.reminder(a)["state"]=="pending"
        s.set_local("2026-03-04","09:55"); s.run_job(); assert not s.sent
        s.set_local("2026-03-04","10:00"); s.run_job(); assert len(s.sent)==1 and s.reminder(a)["state"]=="sent"
    finally:
        s.close()
