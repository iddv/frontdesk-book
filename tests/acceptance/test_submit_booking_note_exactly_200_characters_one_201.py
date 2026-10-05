"""Submit a booking note of exactly 200 characters, then one of 201 characters.

Expected: 200 is accepted; 201 is refused with a field error.
Source: "Booking note: maximum 200 characters"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_submit_booking_note_exactly_200_characters_one_201():
    s = System().basic()
    try:
        a,_=s.book(D1,"10:00",note="x"*200); b,r=s.book(D1,"11:00",note="y"*201); assert a and b is None and "200" in r.text
    finally:
        s.close()
