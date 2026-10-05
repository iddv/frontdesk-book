"""Flow F3: Manage patients.

Flow: F3 in SCOPE.md.
"""

from _helpers.driver import System, unescape

def test_flow_f3_manage_patients():
    s = System().basic()
    try:
        pid, r = s.add_patient("Cara", "Doe", "cara@example.com", "07700 555 123", dob="1980-01-01", force=False)
        assert pid
        r = s.admin.get("/patients", q="555 1")
        assert "Doe" in r.text
        r = s.admin.get("/patients", q="5551")
        assert "Doe" in r.text
        v = s.conn.execute("SELECT version FROM patients WHERE id=?", (pid,)).fetchone()[0]
        r = s.admin.post("/patients/%d" % pid, {"first_name": "Cara", "last_name": "Doe-Smith", "email": "cara@example.com", "phone": "07700 555 123", "dob": "1980-01-01", "send_reminders": "1", "version": v})
        assert "Doe-Smith" in r.text
        pid2, r = s.add_patient("Cara", "Doe-Smith", "other@example.com", "07999 000111", dob="1980-01-01", force=False)
        assert pid2 == pid and ("Use existing" in r.text or "Create anyway" in r.text)
        aid, _ = s.book("2026-03-05", "10:00", pat=pid)
        v = s.conn.execute("SELECT version FROM patients WHERE id=?", (pid,)).fetchone()[0]
        r = s.admin.post("/patients/%d/archive" % pid, {"archived": "1", "version": v})
        assert s.conn.execute("SELECT archived FROM patients WHERE id=?", (pid,)).fetchone()[0] in (0, None)
        s.cancel(aid)
        v = s.conn.execute("SELECT version FROM patients WHERE id=?", (pid,)).fetchone()[0]
        r = s.admin.post("/patients/%d/archive" % pid, {"archived": "1", "version": v})
        assert s.conn.execute("SELECT archived FROM patients WHERE id=?", (pid,)).fetchone()[0] == 1
        assert "Doe-Smith" not in s.admin.get("/patients", q="Cara").text
        assert "Doe-Smith" in s.admin.get("/patients", q="Cara", archived="1").text
    finally:
        s.close()
