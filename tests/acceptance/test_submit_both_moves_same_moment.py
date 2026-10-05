"""Submit both moves at the same moment.

Expected: Only one move succeeds; the other appointment stays at its original time with a conflict message.
Source: "The overlap check and the save happen in one atomic step"
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_submit_both_moves_same_moment():
    s = System().basic()
    try:
        import threading
        a,_=s.book(D1,"09:00"); b,_=s.book(D1,"12:00",pat=s.p2); c2=s.receptionist(); res=[]
        t=[threading.Thread(target=lambda: res.append(s.move(a,D1,"15:00"))), threading.Thread(target=lambda: res.append(s.move(b,D1,"15:00",client=c2)))]
        [x.start() for x in t]; [x.join() for x in t]
        assert s.conn.execute("SELECT COUNT(*) FROM appointments WHERE start_utc='2026-03-04 15:00:00'").fetchone()[0]==1
    finally:
        s.close()
