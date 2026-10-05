"""Its reminder is sent.

Expected: Email contains first name, date, time, practitioner, clinic name, address, phone and the 'to change or cancel, call' line; it does not contain the type name or the note.
Source: "It never includes the type, the booking note or any clinical text."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_reminder_sent():
    s = System().basic()
    try:
        s.admin.post("/admin/clinic",{"name":"Test Clinic","address":"1 High St","phone":"020 7946 0000","reply_to":"","version":1})
        a,_=s.book("2026-03-02","15:00",note="knee pain"); s.run_job(); b=s.sent[0]["body"]
        for w in ("Ann","Monday 2 March 2026","15:00","Dr A","Test Clinic","1 High St","020 7946 0000","to change or cancel, call 020 7946 0000"): assert w.lower() in b.lower(), w
        assert "Consult" not in b and "knee" not in b
    finally:
        s.close()
