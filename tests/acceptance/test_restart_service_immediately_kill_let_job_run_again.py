"""Restart the service immediately (or kill it) and let the job run again.

Expected: No duplicate email; the send log shows one send.
Source: "Its send is recorded before the job moves on, so a restart never sends a duplicate."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_restart_service_immediately_kill_let_job_run_again():
    s = System().basic()
    try:
        a,_=s.book("2026-03-02","15:00"); s.run_job(); s.restart(); s.clock.advance(minutes=5); s.run_job(); assert len(s.sent)==1
    finally:
        s.close()
