"""Flow F2: Set up the clinic and staff.

Flow: F2 in SCOPE.md.
"""

import re
from _helpers.driver import System, Client, PW, unescape

def test_flow_f2_set_up_clinic_staff():
    s = System()
    try:
        r = s.admin.post("/admin/clinic", {"name": "Sunny Clinic", "address": "1 High St", "phone": "020 7946 0000", "reply_to": "desk@example.com", "version": 1})
        assert "Sunny Clinic" in r.text
        pa = s.add_practitioner("Dr Who", {0: "09:00-12:00, 13:00-17:00"})
        r = s.admin.post("/admin/practitioners/%d/timeoff" % pa, {"start_date": "2026-03-03", "end_date": "2026-03-03", "label": "Leave"})
        r = s.admin.get("/day", date="2026-03-03")
        assert "Dr Who" in r.text and "Leave" in r.text
        ty = s.add_type("Checkup", 20)
        assert "Checkup" in s.admin.get("/appt/new", date="2026-03-04", patient_id=s.add_patient()[0]).text
        r = s.admin.post("/admin/email/test", {"to": "me@example.com"})
        import os
        assert os.path.exists(os.path.join(s.dir, "outbox.log")) and "me@example.com" in open(os.path.join(s.dir, "outbox.log")).read()
        rc = s.receptionist()
        assert "<h1>Day" in rc.get("/day").text or "Day" in rc.get("/day").text
        r = rc.get("/admin/practitioners")
        assert r.status == 403 and "Not allowed" in r.text
        r = s.admin.post("/admin/settings", {"booking.outside_hours": "block", "booking.patient_overlap": "warn", "reminders.cancellation_email": "on", "patients.reminder_default": "on"})
        assert s.conn.execute("SELECT value FROM settings WHERE key='booking.outside_hours'").fetchone()[0] == "block"
    finally:
        s.close()
