"""Flow F6: Cancel, close and undo.

Flow: F6 in SCOPE.md.
"""

from _helpers.driver import System, unescape

def test_flow_f6_cancel_close_undo():
    s = System().basic()
    try:
        aid, _ = s.book("2026-03-03", "07:30", confirm=True)  # 23.5h ahead -> late
        assert s.reminder(aid)["state"] in ("pending",)
        s.cancel(aid, "other", "car broke")
        a = s.appt(aid)
        assert a["status"] == "cancelled" and a["late_cancel"] == 1 and a["cancel_text"] == "car broke"
        assert s.reminder(aid)["state"] == "not_needed"
        b, _ = s.book("2026-03-03", "07:30", pat=s.p2, confirm=True)
        assert b
        r = s.undo(aid)
        assert "Conflicts with" in unescape(r.text) and s.appt(aid)["status"] == "cancelled"
        c, _ = s.book("2026-03-02", "10:00")
        s.status(c, "attended")
        assert s.appt(c)["status"] == "booked"
        s.set_local("2026-03-02", "10:00")
        s.status(c, "no_show")
        assert s.appt(c)["status"] == "no_show"
        s.undo(c)
        assert s.appt(c)["status"] == "booked"
        day = s.admin.get("/day", date="2026-03-02").text
        assert "attended" in day and "no_show" in day  # offered directly on the day view
    finally:
        s.close()
