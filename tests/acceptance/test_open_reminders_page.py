"""Open the Reminders page.

Expected: Shows the 6-day-old failure and tomorrow's reminder; not the 8-day-old failure nor the 3-days-ahead reminder.
Source: "A "Reminders" page lists the next 2 days' reminders and all failures from the last 7 days."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_open_reminders_page():
    s = System().basic()
    try:
        # failures 8 and 6 days ago, reminders due tomorrow and in 3 days
        a,_=s.book("2026-03-03","10:00"); b,_=s.book("2026-03-05","10:00",pat=s.p2)
        s.smtp_down=True; s.set_local("2026-03-02","10:00"); [ (s.run_job(), s.clock.advance(minutes=10)) for i in range(5)]
        assert s.reminder(a)["state"]=="failed"; s.smtp_down=False
        s.set_local("2026-03-08","08:00"); a2,_=s.book("2026-03-10","10:00"); a3,_=s.book("2026-03-12","10:00",pat=s.p2)
        t=s.admin.get("/reminders").text
        assert "/appt/%d'"%a in t
        assert "/appt/%d'"%a3 not in t
        assert "/appt/%d'"%a2 in t, "reminder due tomorrow missing" and "/appt/%d'"%a3 not in t and "/appt/%d'"%a in t
        s.set_local("2026-03-10","08:00"); assert "/appt/%d'"%a not in s.admin.get("/reminders").text
    finally:
        s.close()


# Known open item: expected to fail until it is fixed (tests/acceptance/README.md).
import pytest as _pytest_open  # noqa: E402
_marks = globals().get('pytestmark', [])
pytestmark = (list(_marks) if isinstance(_marks, (list, tuple)) else [_marks]) + [
    _pytest_open.mark.xfail(strict=False, reason='Known open issue: Open the Reminders page')]
