"""Both submit a booking for the same practitioner and overlapping time at the same moment.

Expected: Exactly one appointment is saved; the other user receives the conflict message.
Source: "two receptionists booking the same slot at the same moment yield exactly one booking. The other user sees the conflict."
"""

from _helpers.driver import System, Client, PW, D, unescape
D1 = "2026-03-04"


def test_both_submit_booking_same_practitioner_overlapping_time_same():
    s = System().basic()
    try:
        import threading
        c2=s.receptionist(); res=[]
        t=[threading.Thread(target=lambda c=c,p=p: res.append(s.book(D1,"11:00",pat=p,client=c))) for c,p in ((s.admin,s.p1),(c2,s.p2))]
        [x.start() for x in t]; [x.join() for x in t]
        assert sum(1 for a,_ in res if a)==1 and sum(1 for a,r in res if not a and "Conflicts with" in r.text)==1
    finally:
        s.close()
