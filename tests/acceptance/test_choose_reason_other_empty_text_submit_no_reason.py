"""Choose reason 'other' with empty text, or submit no reason.

Expected: Refused with a field error; the appointment stays Booked.
Source: "picking a reason: patient cancelled, clinic cancelled, or other (with a short text)"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_choose_reason_other_empty_text_submit_no_reason():
    s = System().basic()
    try:
        a,_=s.book(D1,"10:00"); s.cancel(a,"other",""); s.cancel(a,""); assert s.appt(a)["status"]=="booked"
    finally:
        s.close()
