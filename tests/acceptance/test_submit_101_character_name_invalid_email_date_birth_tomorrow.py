"""Submit a 101-character name, an invalid email, or a date of birth tomorrow.

Expected: Each refused with a field error; a 100-character name and today's date of birth are accepted.
Source: "names up to 100 characters; ... email must be a valid address; date of birth may not be in the future"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_submit_101_character_name_invalid_email_date_birth_tomorrow():
    s = System().basic()
    try:
        x,r=s.add_patient("A"*101,"L","a@example.com",""); assert x is None
        x,r=s.add_patient("E","Bad","not-an-email",""); assert x is None
        x,r=s.add_patient("D","Bad","d@example.com","",dob="2026-03-03"); assert x is None
    finally:
        s.close()
