"""Let the job run for 40+ minutes.

Expected: Retries occur 10 minutes apart, then the reminder shows Failed and appears in the Reminders page failures; every attempt is logged.
Source: "the send is retried 3 times, 10 minutes apart (default), then marked Failed"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_let_job_run_40_minutes():
    s = System().basic()
    try:
        a,_=s.book("2026-03-05","10:00"); s.smtp_down=True; s.set_local("2026-03-04","10:00")
        times=[]
        for i in range(50):
            if s.run_job(): times.append(i)
            s.clock.advance(minutes=1)
        assert times==[0,10,20,30] and s.reminder(a)["state"]=="failed"
    finally:
        s.close()
