"""Request Undo on it.

Expected: Refused; nothing changes.
Source: ""Undo" on a cancelled, attended or no-show appointment returns it to Booked."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_request_undo():
    s = System().basic()
    try:
        a,_=s.book(D1,"10:00"); v=s.version(a); s.undo(a); assert s.appt(a)["status"]=="booked" and s.version(a)==v
    finally:
        s.close()
