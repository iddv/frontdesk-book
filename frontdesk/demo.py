"""Demo data, loaded only on an empty install."""
import datetime as dt
import random
import secrets

from . import domain as D
from .db import tx

FIRST = ["Alice", "Ben", "Chloe", "Daniel", "Ella", "Finn", "Grace", "Harry", "Isla", "Jack", "Katie", "Liam", "Mia", "Noah",
         "Olivia", "Peter", "Quinn", "Ruby", "Sam", "Tara", "Umar", "Vera", "Will", "Xena", "Yusuf", "Zoe", "Amir", "Bella", "Carl", "Dina"]
LAST = ["Smith", "Jones", "Taylor", "Brown", "Wilson", "Evans", "Thomas", "Roberts", "Walker", "Wright", "Hughes", "Green",
        "Hall", "Wood", "Clarke", "Patel", "Khan", "Lewis", "Young", "King"]


def load(conn, now=None, rng=None):
    now = now or D.utcnow()
    rng = rng or random.Random(42)
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] or conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]:
        raise SystemExit("Refusing to load demo data: the database is not empty. Nothing was changed.")
    tzname = D.machine_tz()
    pw_admin, pw_rec = secrets.token_urlsafe(9), secrets.token_urlsafe(9)
    with tx(conn):
        conn.execute("INSERT INTO clinic(id,name,tz,address,phone,reply_to,email_mode,demo) VALUES(1,?,?,?,?,?,'log',1)",
                     ("Riverside Demo Clinic", tzname, "1 River Road, Exampletown", "+44 20 7946 0000", "desk@example.com"))
        admin = conn.execute("INSERT INTO users(username,role,pw_hash,created_at) VALUES('demo-admin','admin',?,?)",
                             (D.hash_password(pw_admin), D.to_s(now))).lastrowid
        conn.execute("INSERT INTO users(username,role,pw_hash,created_at) VALUES('demo-reception','receptionist',?,?)",
                     (D.hash_password(pw_rec), D.to_s(now)))
    user = {"id": admin}
    prs = []
    for name, title, colour, hours in (
            ("Anna Morgan", "Dr", "#4a90d9", {0: "09:00-12:30, 13:30-17:00", 1: "09:00-17:00", 2: "09:00-17:00", 3: "09:00-17:00", 4: "09:00-13:00"}),
            ("Raj Mehta", "Dr", "#d9822b", {0: "08:00-14:00", 2: "08:00-14:00", 3: "12:00-19:00", 4: "08:00-14:00", 5: "09:00-12:00"}),
            ("Lucy Chen", "", "#3aa76d", {1: "10:00-18:00", 2: "10:00-18:00", 3: "10:00-18:00", 4: "10:00-16:00"})):
        pid = D.save_practitioner(conn, user, {"name": name, "title": title, "colour": colour}, now=now)
        D.set_hours(conn, user, pid, hours, now)
        prs.append(pid)
    today = D.local(D.tz_of(conn), now).date()
    off = today + dt.timedelta(days=(3 - today.weekday()) % 7 + 7)
    D.add_timeoff(conn, user, prs[2], {"start_date": off.isoformat(), "end_date": off.isoformat(), "label": "Leave"}, confirm=True, now=now)
    types = [D.save_type(conn, user, {"name": n, "duration": d}, now=now)
             for n, d in (("Consultation", 30), ("Follow-up", 15), ("Long consultation", 60), ("Check-up", 20))]
    patients = []
    for i in range(60):
        fn, ln = FIRST[i % len(FIRST)], LAST[(i * 7) % len(LAST)]
        dob = dt.date(1940 + rng.randint(0, 70), rng.randint(1, 12), rng.randint(1, 28)).isoformat()
        email = "" if i % 10 == 3 else "%s.%s%d@example.com" % (fn.lower(), ln.lower(), i)
        phone = "+44 7700 9%05d" % (i * 37)
        patients.append(D.create_patient(conn, user, {"first_name": fn, "last_name": ln, "dob": dob, "phone": phone, "email": email,
                                                      "send_reminders": "0" if i % 12 == 5 else "1"}, force=True, now=now))
    # appointments: book them as if "now" were well in the past, then set statuses
    tz = D.tz_of(conn)
    past_clock = now - dt.timedelta(days=30)
    made = 0
    for day_off in range(-14, 15):
        d = today + dt.timedelta(days=day_off)
        for pid in prs:
            hrs = D.hours_for(conn, pid)[d.weekday()]
            for s, e in hrs:
                m = s
                while m < e and made < 150:
                    if rng.random() < 0.21:
                        t = rng.choice(types)
                        dur = conn.execute("SELECT duration FROM appt_types WHERE id=?", (t,)).fetchone()[0]
                        if m + dur <= e:
                            f = {"practitioner_id": pid, "patient_id": rng.choice(patients), "type_id": t, "date": d.isoformat(),
                                 "time": D.hhmm(m), "duration": dur, "note": ""}
                            clock = past_clock if day_off < 0 or rng.random() < 0.5 else now
                            try:
                                aid = D.book(conn, user, f, confirm=True, now=clock)
                                made += 1
                                _settle(conn, user, aid, d, day_off, now, rng)
                            except D.AppError:
                                pass
                            m += dur
                            continue
                    m += 30
    with tx(conn):
        # past reminders: record them as sent so the demo looks lived-in
        conn.execute("UPDATE reminders SET state='sent', sent_at=due_utc, next_attempt_utc=NULL WHERE state='pending' AND due_utc<?", (D.to_s(now),))
    print("Demo data loaded: 3 practitioners, 4 types, 60 patients, %d appointments. Email is in log mode." % made)
    print("  demo-admin      password: %s" % pw_admin)
    print("  demo-reception  password: %s" % pw_rec)
    print("These passwords are shown only once.")


def _settle(conn, user, aid, d, day_off, now, rng):
    a = D.get_appt(conn, aid)
    start = D.from_s(a["start_utc"])
    r = rng.random()
    if r < 0.12:
        D.cancel(conn, user, aid, rng.choice(["patient", "clinic"]), "", a["version"], now=start - dt.timedelta(hours=rng.choice([2, 48])))
    elif start < now:
        D.set_status(conn, user, aid, "no_show" if r < 0.2 else "attended", a["version"], now=max(start, now - dt.timedelta(days=1)) if start < now else now)
