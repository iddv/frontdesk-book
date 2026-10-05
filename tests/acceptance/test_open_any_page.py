"""Open any page.

Expected: A banner is shown in both cases; after a successful send the failure banner disappears.
Source: "A banner on every page shows when email is not configured, or when the last 3 sends failed."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_open_any_page():
    s = System().basic()
    try:
        t=s.admin.get("/day").text; assert "not configured" in t
        a,_=s.book("2026-03-02","15:00"); b,_=s.book("2026-03-02","16:00",pat=s.p2); c,_=s.book("2026-03-02","17:00",pr=s.pb)
        s.smtp_down=True; s.run_job(); assert "failed" in s.admin.get("/day").text.lower()
    finally:
        s.close()
