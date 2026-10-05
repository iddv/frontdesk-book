"""Demo data has about 150 appointments.

Expected: at least 100 appointments after demo load
Source: "about 150 appointments across the past 2 weeks and the next 2 weeks"
"""

import tempfile
from frontdesk import db, demo

def test_demo_data_has_about_150_appointments():
    d = tempfile.mkdtemp(); db.migrate(d, log=lambda *a: None); c = db.connect(db.db_path(d))
    demo.load(c)
    assert 100 <= c.execute("SELECT COUNT(*) FROM appointments").fetchone()[0] <= 200
