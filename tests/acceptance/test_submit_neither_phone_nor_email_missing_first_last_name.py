"""Submit with neither phone nor email, or with missing first or last name.

Expected: Refused with field-level errors; nothing saved.
Source: "first and last name (required)... At least one of phone or email is required."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_submit_neither_phone_nor_email_missing_first_last_name():
    s = System().basic()
    try:
        x,r=s.add_patient("Zed","Zulu","",""); assert x is None and "phone or email" in r.text.lower()
        y,r=s.add_patient("","Nofirst","n@example.com",""); assert y is None
    finally:
        s.close()
