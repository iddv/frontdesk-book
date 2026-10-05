"""Flow F8: Day sheet, export and backup.

Flow: F8 in SCOPE.md.
"""

import csv, io, os, subprocess, sys
from _helpers.driver import System, unescape
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_flow_f8_day_sheet_export_backup():
    s = System().basic()
    try:
        a, _ = s.book("2026-03-04", "10:00"); b, _ = s.book("2026-03-04", "11:00", pat=s.p2); c, _ = s.book("2026-03-04", "10:00", pr=s.pb, pat=s.p2, confirm=True)
        s.cancel(b)
        sheet = unescape(s.admin.get("/daysheet", date="2026-03-04").text)
        assert "Dr A" in sheet and "Dr B" in sheet and "Totals" in sheet and "Cancelled: 1" in sheet
        r = s.admin.get("/export", **{"from": "2026-03-01", "to": "2026-03-31", "download": "1"})
        rows = list(csv.DictReader(io.StringIO(r.text)))
        assert len(rows) == 3
        summ = unescape(s.admin.get("/summary", **{"from": "2026-03-01", "to": "2026-03-31"}).text)
        assert "Dr A" in summ
        assert "No appointments" in s.admin.get("/export", **{"from": "2027-01-01", "to": "2027-01-02"}).text
        bk = s.admin.get("/admin/backup/download")
        assert bk.status == 200 and len(bk.body) > 1000
        f = os.path.join(s.dir, "dl.db"); open(f, "wb").write(bk.body)
        s.book("2026-03-06", "10:00")
        s.conn.close()
        out = subprocess.run([sys.executable, os.path.join(REPO, "frontdesk.py"), "restore", f], env=dict(os.environ, FRONTDESK_DATA_DIR=s.dir), capture_output=True, text=True)
        assert out.returncode == 0, out.stdout + out.stderr
        import sqlite3
        k = sqlite3.connect(os.path.join(s.dir, "frontdesk.db"))
        assert k.execute("SELECT COUNT(*) FROM appointments").fetchone()[0] == 3
        assert k.execute("SELECT COUNT(*) FROM patients").fetchone()[0] == 2
        assert any(x.startswith("replaced-") for x in os.listdir(s.dir))
    finally:
        from frontdesk import db
        s.conn = db.connect(os.path.join(s.dir, "frontdesk.db")); s.close()
