"""Undo it.

Expected: Refused due to the undo limit.
Source: "Undoing anything older than the undo limit: refused (see Domain rules)."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_undo():
    s = System().basic()
    try:
        a,_=s.book("2026-03-02","10:00"); s.set_local("2026-03-02","10:00"); s.status(a,"attended")
        s.set_local("2026-03-20","10:00"); s.undo(a); assert s.appt(a)["status"]=="attended"
    finally:
        s.close()
