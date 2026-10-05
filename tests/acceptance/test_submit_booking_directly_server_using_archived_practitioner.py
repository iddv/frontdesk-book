"""Submit a booking directly to the server using the archived practitioner or type.

Expected: Refused with a clear error; nothing saved.
Source: common practice for this kind of product.
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_submit_booking_directly_server_using_archived_practitioner():
    s = System().basic()
    try:
        pc=s.add_practitioner("Dr C",{i:"08:00-18:00" for i in range(7)})
        s.admin.post("/admin/practitioners/%d/archive"%pc,{"archived":"1","version":1,"confirm":"1"})
        assert s.conn.execute("SELECT archived FROM practitioners WHERE id=?",(pc,)).fetchone()[0]==1
        a,r=s.book(D1,"10:00",pr=pc); assert a is None
        s.admin.post("/admin/types/%d/archive"%s.ty,{"archived":"1"}); b,r=s.book(D1,"10:00"); assert b is None
    finally:
        s.close()
