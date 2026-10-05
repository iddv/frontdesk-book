"""Attempt to move it (including via a direct server request).

Expected: Refused; the appointment is unchanged.
Source: "Only Booked can be moved."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_attempt_move_including_via_direct_server_request():
    s = System().basic()
    try:
        a,_=s.book(D1,"10:00"); s.cancel(a); r=s.move(a,D1,"11:00"); assert s.appt(a)["start_utc"]=="2026-03-04 10:00:00"
        assert "/appt/%d/move"%a not in s.admin.get("/appt/%d"%a).text
    finally:
        s.close()
