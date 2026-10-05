"""Start the service.

Expected: The reminder is sent once on catch-up.
Source: "on start the job sends any reminder still due if the appointment is more than 1 hour away"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_start_service():
    s = System().basic()
    try:
        a,_=s.book("2026-03-05","10:00"); s.set_local("2026-03-05","05:00"); s.restart(); s.run_job()
        assert len(s.sent)==1 and s.reminder(a)["state"]=="sent"
    finally:
        s.close()
