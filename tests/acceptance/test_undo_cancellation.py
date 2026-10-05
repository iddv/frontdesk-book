"""Undo the cancellation.

Expected: Conflict shown; the appointment stays Cancelled.
Source: "Undoing a cancellation when the slot has since been taken: the conflict is shown and the appointment stays Cancelled"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_undo_cancellation():
    s = System().basic()
    try:
        a,_=s.book(D1,"10:00"); s.cancel(a); b,_=s.book(D1,"10:00",pat=s.p2); r=s.undo(a)
        assert "Conflicts with" in r.text and s.appt(a)["status"]=="cancelled"
    finally:
        s.close()
