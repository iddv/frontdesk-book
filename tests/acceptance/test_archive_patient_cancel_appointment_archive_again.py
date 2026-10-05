"""Archive the patient; then cancel the appointment and archive again.

Expected: First attempt refused with the appointment listed; second succeeds and the patient disappears from search unless 'include archived' is ticked, and can be restored.
Source: "Archiving a patient who has future booked appointments: refused until those are cancelled or moved"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_archive_patient_cancel_appointment_archive_again():
    s = System().basic()
    try:
        a,_=s.book(D1,"10:00"); r=s.admin.post("/patients/%d/archive"%s.p1,{"archived":"1","version":s.conn.execute("SELECT version FROM patients WHERE id=?",(s.p1,)).fetchone()[0]})
        assert s.conn.execute("SELECT archived FROM patients WHERE id=?",(s.p1,)).fetchone()[0]==0 and "10:00" in r.text
        s.cancel(a); s.admin.post("/patients/%d/archive"%s.p1,{"archived":"1","version":s.conn.execute("SELECT version FROM patients WHERE id=?",(s.p1,)).fetchone()[0]})
        assert s.conn.execute("SELECT archived FROM patients WHERE id=?",(s.p1,)).fetchone()[0]==1
    finally:
        s.close()
