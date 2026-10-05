"""On service start an interrupted (sending) reminder is marked Failed, never re-sent.

Expected: state failed, no outbox email
Source: "Its send is recorded before the job moves on, so a restart never sends a duplicate"
"""

import os, tempfile, threading
from _helpers.driver import System, D
from frontdesk.app import App

class Wake:
    def __init__(self, app): self.app, self.waits = app, []
    def wait(self, t): self.waits.append(t); self.app.stop.set(); return True
    def clear(self): pass
    def set(self): pass

def run_once(s):
    app = App(s.cfg); w = Wake(app); app.wake = w
    app.reminder_loop(); return w


def test_service_start_interrupted_sending_reminder_marked_failed():
    s = System().basic()
    try:
        a, _ = s.book("2026-03-02", "15:00")
        s.conn.execute("UPDATE reminders SET state='sending' WHERE appointment_id=?", (a,)); s.conn.commit()
        run_once(s)
        assert s.reminder(a)["state"] == "failed"
        assert not os.path.exists(os.path.join(s.dir, "outbox.log"))
    finally:
        s.close()
