"""Flow F5: View the day and move appointments.

Flow: F5 in SCOPE.md.
"""

from _helpers.driver import System, Client, PW, unescape

def test_flow_f5_view_day_move_appointments():
    s = System().basic()
    try:
        aid, _ = s.book("2026-03-04", "10:00")
        d = s.admin.get("/day", date="2026-03-04").text
        assert "date=2026-03-03" in d and "date=2026-03-05" in d
        w = s.admin.get("/week", pr=s.pa, date="2026-03-04").text
        assert "Ann Lee" in w and "date=2026-03-09" in w
        r = s.move(aid, "2026-03-05", "14:00")
        t = unescape(r.text)
        assert "Wed 4 Mar" in t and "Thu 5 Mar" in t and "14:00" in t
        assert "Ann Lee" in s.admin.get("/day", date="2026-03-05").text
        old_v = s.version(aid)
        s.move(aid, "2026-03-05", "15:00")
        r = s.move(aid, "2026-03-05", "16:00", version=old_v)
        assert "was changed by admin; reload" in unescape(r.text)
        assert s.appt(aid)["start_utc"] == "2026-03-05 15:00:00"
    finally:
        s.close()
