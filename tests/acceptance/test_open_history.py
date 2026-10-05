"""Open its history.

Expected: An entry shows the user, the time, and old (10:00) and new (14:00) times.
Source: "records the old and new times in the history"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_open_history():
    s = System().basic()
    try:
        a,_=s.book(D1,"10:00"); r=s.move(a,D1,"14:00"); t=unescape(r.text)
        assert "moved" in t and "10:00" in t and "14:00" in t and "admin" in t
    finally:
        s.close()
