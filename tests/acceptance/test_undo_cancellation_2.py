"""Undo the cancellation.

Expected: It returns to Booked, blocks the slot again, and the history records both the cancel and the undo.
Source: ""Undo" on a cancelled, attended or no-show appointment returns it to Booked."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_undo_cancellation_2():
    s = System().basic()
    try:
        a,_=s.book(D1,"10:00"); s.cancel(a); s.undo(a); assert s.appt(a)["status"]=="booked"
        b,r=s.book(D1,"10:00",pat=s.p2); assert b is None
        assert "undo" in s.admin.get("/appt/%d"%a).text and s.reminder(a)["state"]=="pending"
    finally:
        s.close()
