"""A demo install always uses log mode, even if SMTP is set.

Expected: effective email_mode is log
Source: "log (... always the mode in demo)"
"""

from _helpers.driver import System
from frontdesk import mailer

def test_demo_install_always_uses_log_mode_even_if_smtp_set():
    s = System()
    try:
        s.conn.execute("UPDATE clinic SET demo=1, email_mode='smtp', smtp_host='mail.example.com'"); s.conn.commit()
        assert mailer.effective(s.conn, s.cfg)["email_mode"] == "log"
    finally:
        s.close()
