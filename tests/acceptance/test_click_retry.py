"""Click Retry.

Expected: The reminder is sent, state becomes Sent, and the attempt is logged.
Source: "The user can retry a failed reminder"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_click_retry():
    s = System().basic()
    try:
        a,_=s.book("2026-03-05","10:00"); s.smtp_down=True; s.set_local("2026-03-04","10:00")
        for i in range(4): s.run_job(); s.clock.advance(minutes=10)
        rid=s.reminder(a)["id"]; s.smtp_down=False; s.admin.post("/reminders/%d/retry"%rid); s.run_job()
        assert s.reminder(a)["state"]=="sent" and s.conn.execute("SELECT COUNT(*) FROM email_log WHERE appointment_id=?",(a,)).fetchone()[0]==5
    finally:
        s.close()
