"""User X saves a change based on the version they opened.

Expected: Rejected with a 'changed by someone else' message naming Y; nothing saved.
Source: "A save made against a stale version is rejected with a "changed by someone else" message."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_user_x_saves_change_based_version_they_opened():
    s = System().basic()
    try:
        a,_=s.book(D1,"10:00"); v=s.version(a); c2=s.receptionist(); s.move(a,D1,"12:00",client=c2)
        r=s.cancel(a,version=v); assert "This appointment was changed by rita; reload" in unescape(r.text) and s.appt(a)["status"]=="booked"
    finally:
        s.close()
