"""The reminder job loop waits at most 60 seconds between runs.

Expected: wait timeout is 60s
Source: "A background job in the service runs every minute"
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


def test_reminder_job_loop_waits_most_60_seconds_between_runs():
    s = System()
    try:
        w = run_once(s)
        assert w.waits and w.waits[0] <= 60
    finally:
        s.close()
