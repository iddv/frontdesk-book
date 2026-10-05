"""Submit a phone with 5 digits, 21 digits, letters, or a '+' not at the start; and separately '+31 6-1234' style with 6–20 digits.

Expected: Invalid phones refused with a field error; valid ones accepted.
Source: "phone 6–20 digits, optional leading +, with spaces and dashes allowed"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_submit_phone_5_digits_21_digits_letters_not_start_separately():
    s = System().basic()
    try:
        for ph in ("12345","1"*21,"0770abc123","07700+900123"):
            x,r=s.add_patient("P","Bad"+str(len(ph)),"",ph); assert x is None, ph
        y,r=s.add_patient("P","Good","","+31 6-1234"); assert y
    finally:
        s.close()
