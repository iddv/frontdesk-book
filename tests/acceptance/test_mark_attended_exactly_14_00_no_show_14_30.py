"""Mark it Attended at exactly 14:00, or No-show at 14:30.

Expected: Accepted and recorded in history.
Source: "Attended and No-show can be set only from the start time onward."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_mark_attended_exactly_14_00_no_show_14_30():
    s = System().basic()
    try:
        a,_=s.book("2026-03-02","14:00"); b,_=s.book("2026-03-02","14:00",pr=s.pb,pat=s.p2)
        s.set_local("2026-03-02","14:00"); s.status(a,"attended"); s.set_local("2026-03-02","14:30"); s.status(b,"no_show")
        assert s.appt(a)["status"]=="attended" and s.appt(b)["status"]=="no_show"
    finally:
        s.close()
