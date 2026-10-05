"""Book P with practitioner B at 10:15.

Expected: Refused.
Source: "Whether a patient may hold two overlapping appointments with different practitioners."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_book_p_practitioner_b_10_15():
    s = System().basic()
    try:
        s.settings(booking__patient_overlap="block"); a,_=s.book(D1,"10:00")
        b,r=s.book(D1,"10:15",pr=s.pb,confirm=True); assert b is None and "already has an appointment" in r.text
    finally:
        s.close()
