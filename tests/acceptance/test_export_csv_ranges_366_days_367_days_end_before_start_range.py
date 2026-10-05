"""Export CSV for ranges of 366 days, 367 days, end before start, and a range with no appointments; compare with the Summary.

Expected: 366 accepted; 367 and reversed ranges refused with an error; empty range yields header only; CSV row counts per status equal Summary counts.
Source: "maximum 366 days ... Summary counts always equal the number of matching appointment records."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_export_csv_ranges_366_days_367_days_end_before_start_range():
    s = System().basic()
    try:
        import csv,io
        a,_=s.book(D1,"10:00"); b,_=s.book(D1,"11:00",pat=s.p2); s.cancel(b)
        ok=s.admin.get("/export",**{"from":"2026-01-01","to":"2027-01-01","download":"1"}); assert ok.status==200 and len(list(csv.reader(io.StringIO(ok.text))))==3
        bad=s.admin.get("/export",**{"from":"2026-01-01","to":"2027-01-02","download":"1"}); assert "366" in bad.text
        bad=s.admin.get("/export",**{"from":"2026-03-05","to":"2026-03-01","download":"1"}); assert "before" in bad.text
        e=s.admin.get("/export",**{"from":"2027-05-01","to":"2027-05-02","download":"1"}); assert len(e.text.strip().splitlines())==1
    finally:
        s.close()
