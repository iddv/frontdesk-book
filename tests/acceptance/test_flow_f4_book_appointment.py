"""Flow F4: Book an appointment.

Flow: F4 in SCOPE.md.
"""

import threading
from _helpers.driver import System, Client, PW, unescape

def test_flow_f4_book_appointment():
    s = System().basic()
    try:
        aid, r = s.book("2026-03-04", "10:00", note="call first")
        assert aid and "Reminder due Tue 3 Mar 10:00" in unescape(r.text)
        day = unescape(s.admin.get("/day", date="2026-03-04").text)
        assert "Ann Lee" in day and "Reminder due" in day
        b = s.receptionist()
        res = []
        def go(c, pat):
            res.append(s.book("2026-03-04", "14:00", pat=pat, client=c))
        t = [threading.Thread(target=go, args=(s.admin, s.p1)), threading.Thread(target=go, args=(b, s.p2))]
        [x.start() for x in t]; [x.join() for x in t]
        ok = [a for a, _ in res if a]
        conflicts = [r for a, r in res if not a and "Conflicts with" in r.text]
        assert len(ok) == 1 and len(conflicts) == 1
        assert s.conn.execute("SELECT COUNT(*) FROM appointments WHERE start_utc='2026-03-04 14:00:00'").fetchone()[0] == 1
    finally:
        s.close()
