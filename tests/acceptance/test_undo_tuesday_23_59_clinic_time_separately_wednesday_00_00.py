"""Undo at Tuesday 23:59 clinic time, and separately at Wednesday 00:00.

Expected: Tuesday undo returns it to Booked; Wednesday undo is refused.
Source: "Undo of a status change is allowed until the end of the day after the appointment's date"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_undo_tuesday_23_59_clinic_time_separately_wednesday_00_00():
    s = System().basic()
    try:
        a,_=s.book("2026-03-02","10:00"); b,_=s.book("2026-03-02","11:00",pat=s.p2); s.set_local("2026-03-02","10:00"); s.status(a,"attended")
        s.set_local("2026-03-02","11:00"); s.status(b,"attended")
        s.set_local("2026-03-03","23:59"); s.undo(a); assert s.appt(a)["status"]=="booked"
        s.set_local("2026-03-04","00:00"); s.undo(b); assert s.appt(b)["status"]=="attended"
    finally:
        s.close()
