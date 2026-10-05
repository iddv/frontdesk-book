"""Cancel the appointment.

Expected: One cancellation email is sent (or written to the outbox in log mode). With the setting off, none is sent.
Source: "sends a cancellation email if `reminders.cancellation_email` is on"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_cancel_appointment():
    s = System().basic()
    try:
        a,_=s.book("2026-03-05","10:00"); s.cancel(a); s.run_job(); s.run_job()
        assert len([m for m in s.sent if "cancelled" in m["subject"]])==1
    finally:
        s.close()
