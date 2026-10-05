"""Add a time-off block covering next Tuesday, first without confirming, then confirming.

Expected: Without confirmation the affected appointments are listed and nothing is saved; after confirmation the block is saved, the appointments stay Booked and are flagged "outside hours".
Source: "the system lists those appointments and saves only after the admin confirms. The appointments stay booked and are flagged "outside hours" on the day view."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_add_time_off_block_covering_next_tuesday_first_without():
    s = System().basic()
    try:
        a,_=s.book("2026-03-10","10:00"); f={"start_date":"2026-03-10","end_date":"2026-03-10","label":"Leave"}
        r=s.admin.post("/admin/practitioners/%d/timeoff"%s.pa,f); assert "10:00" in r.text and not s.conn.execute("SELECT 1 FROM timeoff").fetchone()
        f["confirm"]="1"; s.admin.post("/admin/practitioners/%d/timeoff"%s.pa,f); assert s.conn.execute("SELECT 1 FROM timeoff").fetchone()
        assert s.appt(a)["status"]=="booked" and "outside hours" in s.admin.get("/day",date="2026-03-10").text
    finally:
        s.close()
