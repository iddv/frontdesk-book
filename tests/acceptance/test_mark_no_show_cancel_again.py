"""Mark it No-show, or cancel it again.

Expected: Refused; only Booked appointments can be cancelled or closed.
Source: "The user opens a booked appointment and chooses "Cancel""
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_mark_no_show_cancel_again():
    s = System().basic()
    try:
        a,_=s.book("2026-03-02","14:00"); b,_=s.book(D1,"10:00"); s.set_local("2026-03-02","14:00"); s.status(a,"attended")
        s.status(a,"no_show"); s.cancel(b); s.cancel(b,reason="clinic")
        assert s.appt(a)["status"]=="attended" and s.appt(b)["cancel_reason"]=="patient"
    finally:
        s.close()
