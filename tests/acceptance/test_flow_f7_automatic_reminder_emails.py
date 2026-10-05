"""Flow F7: Automatic reminder emails.

Flow: F7 in SCOPE.md.
"""

import datetime as dt
from _helpers.driver import System, unescape

def test_flow_f7_automatic_reminder_emails():
    s = System().basic()
    try:
        aid, _ = s.book("2026-03-05", "10:00")
        s.set_local("2026-03-04", "09:59"); s.run_job(); assert not s.sent
        s.set_local("2026-03-04", "10:00"); s.run_job(); s.run_job()
        assert len(s.sent) == 1 and s.reminder(aid)["state"] == "sent"
        assert s.conn.execute("SELECT COUNT(*) FROM email_log WHERE appointment_id=?", (aid,)).fetchone()[0] == 1
        assert "Reminder sent" in unescape(s.admin.get("/appt/%d" % aid).text)
        # SMTP down
        b, _ = s.book("2026-03-06", "10:00")
        s.smtp_down = True
        s.set_local("2026-03-05", "10:00")
        for i in range(5):
            s.run_job(); s.clock.advance(minutes=10)
        r = s.reminder(b)
        assert r["state"] == "failed"
        assert s.conn.execute("SELECT COUNT(*) FROM email_log WHERE appointment_id=?", (b,)).fetchone()[0] == 4
        page = s.admin.get("/reminders").text
        assert "/reminders/%d/retry" % r["id"] in page
        s.smtp_down = False
        s.admin.post("/reminders/%d/retry" % r["id"])
        s.run_job()
        assert s.reminder(b)["state"] == "sent"
        # downtime catch-up
        c, _ = s.book("2026-03-08", "15:00")
        d, _ = s.book("2026-03-08", "11:00", pat=s.p2)
        s.set_local("2026-03-08", "10:10")
        s.restart()
        assert s.reminder(c)["state"] == "sent"
        assert s.reminder(d)["state"] == "skipped" and s.reminder(d)["reason"] == "too late"
    finally:
        s.close()
