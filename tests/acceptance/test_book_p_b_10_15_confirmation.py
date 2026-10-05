"""Book P with B at 10:15 with confirmation.

Expected: Saved after confirmation; without confirmation, only a warning and nothing saved.
Source: "blocked, or a warning, depending on `booking.patient_overlap`"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_book_p_b_10_15_confirmation():
    s = System().basic()
    try:
        a,_=s.book(D1,"10:00"); b,r=s.book(D1,"10:15",pr=s.pb); assert b is None and "already has" in r.text
        b,_=s.book(D1,"10:15",pr=s.pb,confirm=True); assert b
    finally:
        s.close()
