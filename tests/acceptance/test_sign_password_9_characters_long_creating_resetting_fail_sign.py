"""Sign in with a password 9 characters long when creating/resetting; and fail sign-in 5 times then try the correct password.

Expected: 9-character passwords refused at creation; after 5 failures the correct password is refused until 15 minutes pass, after which it works. 4 failures do not lock.
Source: "at least 10 characters. 5 failed sign-ins lock the account for 15 minutes"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_sign_password_9_characters_long_creating_resetting_fail_sign():
    s = System().basic()
    try:
        s.admin.post("/admin/staff",{"username":"short","role":"receptionist","password":"123456789","password2":"123456789"})
        assert not s.conn.execute("SELECT 1 FROM users WHERE username='short'").fetchone()
        c=Client(s)
        for i in range(4): c.login("admin","wrong-password")
        assert "Sign in" not in c.login("admin",PW).text.split("<h1>")[1][:20]
        c=Client(s)
        for i in range(5): c.login("admin","wrong-password")
        assert "<h1>Sign in" in c.login("admin",PW).text
        s.clock.advance(minutes=15); assert "<h1>Sign in" not in c.login("admin",PW).text
    finally:
        s.close()
