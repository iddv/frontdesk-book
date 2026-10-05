"""SMTP mode without a host counts as not configured and shows the banner.

Expected: banner 'not configured' on day view
Source: "A banner on every page shows when email is not configured"
"""

from _helpers.driver import System

def test_smtp_mode_without_host_counts_not_configured_shows_banner():
    s = System()
    try:
        s.conn.execute("UPDATE clinic SET email_mode='smtp', smtp_host=''"); s.conn.commit()
        assert "not configured" in s.admin.get("/day").text
    finally:
        s.close()
