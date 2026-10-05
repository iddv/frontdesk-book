"""Emails carry the clinic reply-to address.

Expected: outbox message has Reply-To header
Source: "reply-to email. These details appear in reminders"
"""

import os
from _helpers.driver import System

def test_emails_carry_clinic_reply_address():
    s = System().basic()
    try:
        s.admin.post("/admin/clinic", {"name": "Test Clinic", "address": "1 High St", "phone": "020 7946 0000", "reply_to": "desk@example.com", "version": 1})
        s.book("2026-03-02", "15:00"); s.run_job_real()
        box = open(os.path.join(s.dir, "outbox.log")).read()
        assert "Reply-To: desk@example.com" in box
    finally:
        s.close()
