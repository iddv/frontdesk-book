"""Book an appointment for them.

Expected: Reminder state is Skipped with the reason (no email / opted out); no email ever sent; confirmation says no reminder.
Source: "Only patients with an email and with "send reminders" on get emails."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_book_appointment_them():
    s = System().basic()
    try:
        x,_=s.add_patient("No","Mail","","07700 900333"); y,_=s.add_patient("Opt","Out","o@example.com","07700 900444",reminders=False)
        a,r=s.book(D1,"10:00",pat=x); b,_=s.book(D1,"11:00",pat=y)
        assert s.reminder(a)["state"]=="skipped" and s.reminder(a)["reason"]=="no email" and s.reminder(b)["reason"]=="opted out"
        assert "No reminder: no email" in unescape(r.text)
    finally:
        s.close()
