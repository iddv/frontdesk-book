"""Move it to 11:15.

Expected: Conflict shown; appointment stays at 10:00 and its history is unchanged.
Source: "Conflict at the new time: the conflict message is shown and the appointment stays where it was."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_move_11_15():
    s = System().basic()
    try:
        a,_=s.book(D1,"10:00"); b,_=s.book(D1,"11:00",pat=s.p2); r=s.move(a,D1,"11:15")
        assert "Conflicts with" in r.text and s.appt(a)["start_utc"]=="2026-03-04 10:00:00"
    finally:
        s.close()
