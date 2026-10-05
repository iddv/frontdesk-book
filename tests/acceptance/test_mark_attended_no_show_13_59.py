"""Mark it Attended or No-show at 13:59.

Expected: Refused.
Source: "Attended and No-show can be set only from the start time onward."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_mark_attended_no_show_13_59():
    s = System().basic()
    try:
        a,_=s.book("2026-03-02","14:00"); s.set_local("2026-03-02","13:59"); s.status(a,"attended"); s.status(a,"no_show")
        assert s.appt(a)["status"]=="booked"
    finally:
        s.close()
