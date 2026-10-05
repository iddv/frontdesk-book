"""Send direct server requests to change settings, practitioners, hours, staff accounts, or download a backup.

Expected: All refused as not allowed; nothing changes.
Source: "the permissions in Users are enforced on the server for every action, not only hidden in the interface"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_send_direct_server_requests_change_settings_practitioners():
    s = System().basic()
    try:
        c=s.receptionist()
        for path,form in (("/admin/settings",{"booking.outside_hours":"block"}),("/admin/practitioners",{"name":"X"}),("/admin/practitioners/%d/hours"%s.pa,{"day0":"10:00-11:00"}),("/admin/staff",{"username":"evil","role":"admin","password":PW,"password2":PW})):
            assert c.post(path,form).status==403, path
        assert c.get("/admin/backup/download").status==403
        assert s.conn.execute("SELECT value FROM settings WHERE key='booking.outside_hours'").fetchone() in (None,) or s.conn.execute("SELECT value FROM settings WHERE key='booking.outside_hours'").fetchone()[0]=="warn"
    finally:
        s.close()
