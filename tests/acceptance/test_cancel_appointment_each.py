"""Cancel an appointment for each.

Expected: Only the patient with email receives a cancellation email; the other cancellation still succeeds.
Source: "Whether a patient with email gets a short email when their appointment is cancelled."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_cancel_appointment_each():
    s = System().basic()
    try:
        x,_=s.add_patient("No","Mail","","07700 900333"); a,_=s.book(D1,"10:00"); b,_=s.book(D1,"11:00",pat=x)
        s.cancel(a); s.cancel(b); s.run_job(); assert len(s.sent)==1 and s.appt(b)["status"]=="cancelled"
    finally:
        s.close()
