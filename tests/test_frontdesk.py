"""Automated tests: overlap & concurrency, DST, reminder timing, permissions, undo, export, backup."""
import csv
import datetime as dt
import http.client
import io
import os
import re
import shutil
import tempfile
import threading
import unittest
import urllib.parse
from http.server import ThreadingHTTPServer

from frontdesk import config, db, domain as D, web
from frontdesk.app import App

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 3, 2, 8, 0, tzinfo=UTC)   # Monday 2 March 2026, 08:00 London


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        db.migrate(self.dir, log=lambda *_: None)
        self.path = db.db_path(self.dir)
        self.conn = db.connect(self.path)
        D.create_first_admin(self.conn, "Test Clinic", "Europe/London", "admin", "correct-horse", "correct-horse", now=T0)
        self.admin = dict(self.conn.execute("SELECT * FROM users").fetchone())
        self.pr = D.save_practitioner(self.conn, self.admin, {"name": "Dr A"}, now=T0)
        self.pr2 = D.save_practitioner(self.conn, self.admin, {"name": "Dr B"}, now=T0)
        D.set_hours(self.conn, self.admin, self.pr, {i: "08:00-18:00" for i in range(7)}, T0)
        D.set_hours(self.conn, self.admin, self.pr2, {i: "08:00-18:00" for i in range(7)}, T0)
        self.type = D.save_type(self.conn, self.admin, {"name": "Consult", "duration": 30}, now=T0)
        self.pat = self.patient("Ann", "Lee", "ann@example.com")
        self.pat2 = self.patient("Bob", "Ray", "bob@example.com")

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def patient(self, fn, ln, email="", phone="", reminders="1"):
        return D.create_patient(self.conn, self.admin, {"first_name": fn, "last_name": ln, "email": email,
                                                        "phone": phone or "07700 900%03d" % (len(fn + ln) * 7 % 1000),
                                                        "send_reminders": reminders}, force=True, now=T0)

    def book(self, date="2026-03-04", time="10:00", dur=30, pr=None, pat=None, now=T0, confirm=False):
        return D.book(self.conn, self.admin, {"practitioner_id": pr or self.pr, "patient_id": pat or self.pat, "type_id": self.type,
                                              "date": date, "time": time, "duration": dur}, confirm=confirm, now=now)

    def rem(self, aid):
        return D.current_reminder(self.conn, aid)


class OverlapTests(Base):
    def test_overlap_blocked_and_touching_allowed(self):
        self.book(time="10:00")
        with self.assertRaises(D.Conflict) as cm:
            self.book(time="10:15", pat=self.pat2)
        self.assertIn("Conflicts with Ann Lee 10:00–10:30", str(cm.exception))
        self.book(time="10:30", pat=self.pat2)       # touching end/start is fine
        self.book(time="09:30", pat=self.pat2)
        self.book(time="10:00", pr=self.pr2, pat=self.pat2, confirm=True)  # other practitioner

    def test_cancelled_never_blocks(self):
        a = self.book()
        D.cancel(self.conn, self.admin, a, "patient", "", 1, now=T0)
        self.book(pat=self.pat2)

    def test_past_refused(self):
        with self.assertRaises(D.ValidationError):
            self.book(date="2026-03-02", time="07:55")   # 07:55 local < now 08:00
        self.book(date="2026-03-02", time="08:00")

    def test_concurrent_booking_yields_one(self):
        results = []
        barrier = threading.Barrier(8)

        def worker(i):
            c = db.connect(self.path)
            barrier.wait()
            try:
                D.book(c, self.admin, {"practitioner_id": self.pr, "patient_id": self.pat if i % 2 else self.pat2, "type_id": self.type,
                                       "date": "2026-03-05", "time": "11:00", "duration": 30}, confirm=True, now=T0)
                results.append("ok")
            except D.Conflict:
                results.append("conflict")
            finally:
                c.close()
        ts = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(results.count("ok"), 1)
        self.assertEqual(results.count("conflict"), 7)
        n = self.conn.execute("SELECT COUNT(*) FROM appointments WHERE status='booked'").fetchone()[0]
        self.assertEqual(n, 1)

    def test_outside_hours_warn_and_block(self):
        D.set_hours(self.conn, self.admin, self.pr, {0: "09:00-17:00"}, T0)
        with self.assertRaises(D.NeedsConfirm):
            self.book(date="2026-03-03", time="10:00")
        self.book(date="2026-03-03", time="10:00", confirm=True)
        D.set_settings(self.conn, self.admin, {"booking.outside_hours": "block"}, T0)
        with self.assertRaises(D.ValidationError):
            self.book(date="2026-03-03", time="12:00", confirm=True)

    def test_patient_overlap_setting(self):
        self.book(time="10:00")
        with self.assertRaises(D.NeedsConfirm):
            self.book(time="10:00", pr=self.pr2)
        D.set_settings(self.conn, self.admin, {"booking.patient_overlap": "block"}, T0)
        with self.assertRaises(D.Conflict):
            self.book(time="10:00", pr=self.pr2, confirm=True)

    def test_stale_move_rejected(self):
        a = self.book()
        D.move(self.conn, self.admin, a, {"date": "2026-03-04", "time": "11:00", "duration": 30, "version": 1}, now=T0)
        with self.assertRaises(D.Stale):
            D.move(self.conn, self.admin, a, {"date": "2026-03-04", "time": "12:00", "duration": 30, "version": 1}, now=T0)
        hist = [h["action"] for h in self.conn.execute("SELECT * FROM appt_history WHERE appointment_id=?", (a,))]
        self.assertEqual(hist, ["created", "moved"])


class DSTTests(Base):
    def test_spring_forward(self):
        # Europe/London: 29 March 2026 01:00 -> 02:00
        with self.assertRaises(D.ValidationError):
            self.book(date="2026-03-29", time="01:30", confirm=True)
        a = self.book(date="2026-03-29", time="00:30", dur=90, confirm=True)   # 00:30 GMT -> 02:00 BST, 90 real minutes
        row = D.get_appt(self.conn, a)
        self.assertEqual(row["start_utc"], "2026-03-29 00:30:00")
        self.assertEqual(row["end_utc"], "2026-03-29 02:00:00")
        b = self.book(date="2026-03-29", time="10:00", confirm=True)
        self.assertEqual(D.get_appt(self.conn, b)["start_utc"], "2026-03-29 09:00:00")
        rows = D.appts_in_range(self.conn, dt.date(2026, 3, 29), dt.date(2026, 3, 29))
        self.assertEqual(len(rows), 2)

    def test_fall_back_reminder_24h(self):
        a = self.book(date="2026-10-25", time="10:00", confirm=True)  # BST ends 25 Oct 2026
        r = self.rem(a)
        self.assertEqual(r["due_utc"], "2026-10-24 10:00:00")   # exactly 24 real hours before 10:00 GMT


class ReminderTests(Base):
    def setUp(self):
        super().setUp()
        self.sent = []
        self.fail = False

    def send(self, to, subject, body, reply_to):
        if self.fail:
            raise OSError("Connection refused")
        self.sent.append((to, subject, body))

    def test_normal_timing_and_once(self):
        a = self.book(date="2026-03-05", time="10:00")
        r = self.rem(a)
        self.assertEqual((r["state"], r["due_utc"]), ("pending", "2026-03-04 10:00:00"))
        D.process_due(self.conn, self.send, now=dt.datetime(2026, 3, 4, 9, 59, tzinfo=UTC))
        self.assertEqual(self.sent, [])
        D.process_due(self.conn, self.send, now=dt.datetime(2026, 3, 4, 10, 0, tzinfo=UTC))
        D.process_due(self.conn, self.send, now=dt.datetime(2026, 3, 4, 10, 1, tzinfo=UTC))
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.rem(a)["state"], "sent")
        body = self.sent[0][2]
        self.assertIn("Ann", body)
        self.assertNotIn("Consult", body)   # never the type
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM email_log").fetchone()[0], 1)

    def test_inside_window_sent_now_or_too_late(self):
        a = self.book(date="2026-03-02", time="15:00")      # 7h away
        self.assertEqual(self.rem(a)["due_utc"], D.to_s(T0))
        b = self.book(date="2026-03-02", time="09:30", pat=self.pat2)   # 1.5h away
        self.assertEqual((self.rem(b)["state"], self.rem(b)["reason"]), ("skipped", "too late"))

    def test_no_email_and_opt_out(self):
        p = self.patient("No", "Mail", "", "0123456789")
        q = self.patient("Opt", "Out", "o@example.com", reminders="0")
        self.assertEqual(self.rem(self.book(pat=p))["reason"], "no email")
        self.assertEqual(self.rem(self.book(pat=q, time="12:00"))["reason"], "opted out")

    def test_catch_up_after_downtime(self):
        a = self.book(date="2026-03-05", time="10:00")
        b = self.book(date="2026-03-04", time="11:00", pat=self.pat2)
        # computer off from before both due times until 4 Mar 10:30 UTC: a (23.5h away) is sent, b (30 min away) too late
        D.process_due(self.conn, self.send, now=dt.datetime(2026, 3, 4, 10, 30, tzinfo=UTC))
        self.assertEqual(self.rem(a)["state"], "sent")
        self.assertEqual((self.rem(b)["state"], self.rem(b)["reason"]), ("skipped", "too late"))

    def test_move_after_sent_sends_changed(self):
        a = self.book(date="2026-03-05", time="10:00")
        t = dt.datetime(2026, 3, 4, 10, 0, tzinfo=UTC)
        D.process_due(self.conn, self.send, now=t)
        D.move(self.conn, self.admin, a, {"date": "2026-03-06", "time": "10:00", "duration": 30, "version": 1}, now=t)
        r = self.rem(a)
        self.assertEqual((r["kind"], r["state"], r["due_utc"]), ("changed", "pending", "2026-03-05 10:00:00"))
        D.process_due(self.conn, self.send, now=dt.datetime(2026, 3, 5, 10, 0, tzinfo=UTC))
        self.assertEqual(self.sent[-1][1], "Your appointment has changed")

    def test_move_pending_reschedules(self):
        a = self.book(date="2026-03-05", time="10:00")
        D.move(self.conn, self.admin, a, {"date": "2026-03-07", "time": "10:00", "duration": 30, "version": 1}, now=T0)
        r = self.rem(a)
        self.assertEqual((r["kind"], r["due_utc"]), ("reminder", "2026-03-06 10:00:00"))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM reminders WHERE appointment_id=? AND state='pending'", (a,)).fetchone()[0], 1)

    def test_retry_then_failed_then_manual_retry(self):
        a = self.book(date="2026-03-05", time="10:00")
        self.fail = True
        t = dt.datetime(2026, 3, 4, 10, 0, tzinfo=UTC)
        for i in range(4):
            D.process_due(self.conn, self.send, now=t + dt.timedelta(minutes=10 * i))
        r = self.rem(a)
        self.assertEqual((r["state"], r["attempts"]), ("failed", 4))
        self.assertIn("Connection refused", r["reason"])
        self.assertTrue(D.last_sends_failed(self.conn))
        self.fail = False
        D.retry_reminder(self.conn, self.admin, r["id"], now=t + dt.timedelta(hours=1))
        D.process_due(self.conn, self.send, now=t + dt.timedelta(hours=1))
        self.assertEqual(self.rem(a)["state"], "sent")

    def test_cancel_stops_reminder_and_sends_cancellation(self):
        a = self.book(date="2026-03-05", time="10:00")
        late = D.cancel(self.conn, self.admin, a, "patient", "", 1, now=T0)
        self.assertEqual(late, 0)
        self.assertEqual(self.rem(a)["state"], "not_needed")
        D.process_due(self.conn, self.send, now=T0)
        self.assertEqual([s[1] for s in self.sent], ["Your appointment has been cancelled"])

    def test_interrupted_send_not_repeated(self):
        a = self.book(date="2026-03-05", time="10:00")
        self.conn.execute("UPDATE reminders SET state='sending' WHERE appointment_id=?", (a,))
        D.recover_interrupted(self.conn)
        D.process_due(self.conn, self.send, now=dt.datetime(2026, 3, 4, 10, 0, tzinfo=UTC))
        self.assertEqual(self.sent, [])
        self.assertEqual(self.rem(a)["state"], "failed")

    def test_resend_logged(self):
        a = self.book(date="2026-03-05", time="10:00")
        D.resend_reminder(self.conn, self.admin, a, now=T0)
        D.process_due(self.conn, self.send, now=T0)
        log = self.conn.execute("SELECT * FROM email_log").fetchall()
        self.assertEqual(len(log), 1)
        self.assertIn("manual", log[0]["kind"])


class StatusUndoTests(Base):
    def test_attended_only_after_start_and_undo_window(self):
        a = self.book(date="2026-03-02", time="10:00")
        with self.assertRaises(D.ValidationError):
            D.set_status(self.conn, self.admin, a, "attended", 1, now=T0)
        start = dt.datetime(2026, 3, 2, 10, 0, tzinfo=UTC)
        D.set_status(self.conn, self.admin, a, "attended", 1, now=start)
        D.undo(self.conn, self.admin, a, 2, now=dt.datetime(2026, 3, 3, 23, 59, tzinfo=UTC))
        D.set_status(self.conn, self.admin, a, "no_show", 3, now=start)
        with self.assertRaises(D.ValidationError):
            D.undo(self.conn, self.admin, a, 4, now=dt.datetime(2026, 3, 4, 0, 0, tzinfo=UTC))

    def test_undo_cancel_conflict(self):
        a = self.book()
        late = D.cancel(self.conn, self.admin, a, "other", "weather", 1, now=dt.datetime(2026, 3, 3, 12, 0, tzinfo=UTC))
        self.assertEqual(late, 1)
        b = self.book(pat=self.pat2, now=dt.datetime(2026, 3, 3, 12, 0, tzinfo=UTC))
        with self.assertRaises(D.Conflict):
            D.undo(self.conn, self.admin, a, 2, now=dt.datetime(2026, 3, 3, 12, 0, tzinfo=UTC))
        self.assertEqual(D.get_appt(self.conn, a)["status"], "cancelled")
        D.cancel(self.conn, self.admin, b, "clinic", "", 1, now=T0)
        D.undo(self.conn, self.admin, a, 2, now=T0)
        self.assertEqual(D.get_appt(self.conn, a)["status"], "booked")
        self.assertEqual(self.rem(a)["state"], "pending")


class PatientTests(Base):
    def test_validation_duplicates_search_archive(self):
        with self.assertRaises(D.ValidationError) as cm:
            D.create_patient(self.conn, self.admin, {"first_name": "X", "last_name": "Y", "email": "bad", "phone": "12"}, now=T0)
        self.assertIn("email", cm.exception.errors)
        with self.assertRaises(D.ValidationError):
            D.create_patient(self.conn, self.admin, {"first_name": "X", "last_name": "Y"}, now=T0)
        D.create_patient(self.conn, self.admin, {"first_name": "Cat", "last_name": "Doe", "dob": "1980-01-02", "phone": "+44 7700-123456"}, now=T0)
        with self.assertRaises(D.NeedsConfirm):
            D.create_patient(self.conn, self.admin, {"first_name": "cat", "last_name": "DOE", "dob": "1980-01-02", "phone": "0111 222333"}, now=T0)
        self.assertEqual([r["first_name"] for r in D.search_patients(self.conn, "123456", now=T0)], ["Cat"])
        self.assertEqual(len(D.search_patients(self.conn, "1980-01-02", now=T0)), 1)
        self.book()
        with self.assertRaises(D.NeedsConfirm):
            D.archive_patient(self.conn, self.admin, self.pat, True, 1, now=T0)


class ExportTests(Base):
    def test_csv_matches_summary(self):
        a = self.book(time="10:00")
        self.book(time="11:00", pat=self.pat2)
        D.cancel(self.conn, self.admin, a, "patient", "", 1, now=dt.datetime(2026, 3, 3, 12, 0, tzinfo=UTC))
        rows = list(D.export_rows(self.conn, dt.date(2026, 3, 1), dt.date(2026, 3, 31)))
        s = D.summary(self.conn, dt.date(2026, 3, 1), dt.date(2026, 3, 31))["Dr A"]
        self.assertEqual(len(rows), s["total"])
        self.assertEqual(sum(1 for r in rows if r[8] == "Cancelled"), s["cancelled"])
        self.assertEqual(sum(1 for r in rows if r[10] == "yes"), s["late_cancelled"])
        self.assertEqual(list(D.export_rows(self.conn, dt.date(2026, 5, 1), dt.date(2026, 5, 2))), [])
        with self.assertRaises(D.ValidationError):
            D.parse_range({"from": "2026-01-01", "to": "2027-01-02"})
        with self.assertRaises(D.ValidationError):
            D.parse_range({"from": "2026-02-01", "to": "2026-01-01"})

    def test_backup_restore_roundtrip(self):
        self.book()
        dest = os.path.join(self.dir, "b.db")
        db.backup_to(self.conn, dest)
        other = tempfile.mkdtemp()
        try:
            db.restore(other, dest, log=lambda *_: None)
            c = db.connect(db.db_path(other))
            self.assertEqual(c.execute("SELECT COUNT(*) FROM appointments").fetchone()[0], 1)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM patients").fetchone()[0], 2)
            c.close()
        finally:
            shutil.rmtree(other, ignore_errors=True)


class HTTPTests(Base):
    """Server-side permission checks through the real HTTP handler."""

    def setUp(self):
        super().setUp()
        D.create_user(self.conn, self.admin, "rec", "receptionist", "receptionist1", "receptionist1", now=T0)
        self.conn.execute("UPDATE users SET must_change=0")
        cfg = config.Config(config.DEFAULTS)
        cfg["data_dir"] = self.dir
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
        self.server.app = App(cfg)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def req(self, method, path, cookie="", form=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port)
        body = urllib.parse.urlencode(form or {})
        h = {"Cookie": cookie}
        if method == "POST":
            h["Content-Type"] = "application/x-www-form-urlencoded"
        c.request(method, path, body if method == "POST" else None, h)
        r = c.getresponse()
        return r.status, dict(r.getheaders()), r.read().decode("utf-8", "replace")

    def login(self, user, pw):
        _, h, page = self.req("GET", "/login")
        pre = h["Set-Cookie"].split(";")[0]
        csrf = re.search(r'name="_csrf" value="([^"]+)"', page).group(1)
        st, h, _ = self.req("POST", "/login", pre, {"_csrf": csrf, "username": user, "password": pw})
        self.assertEqual(st, 303)
        cookie = h["Set-Cookie"].split(";")[0]
        _, _, page = self.req("GET", "/day", cookie)
        return cookie, re.search(r'name="_csrf" value="([^"]+)"', page).group(1)

    def test_permissions(self):
        st, h, _ = self.req("GET", "/day")
        self.assertEqual((st, h["Location"]), (303, "/login"))
        st, h, _ = self.req("GET", "/setup")
        self.assertEqual(h.get("Location"), "/login")
        rc, rcsrf = self.login("rec", "receptionist1")
        for path in ("/admin/staff", "/admin/settings", "/admin/backup/download", "/admin/email"):
            st, _, body = self.req("GET", path, rc)
            self.assertEqual(st, 403, path)
            self.assertIn("Not allowed", body)
        st, _, _ = self.req("POST", "/admin/staff", rc, {"_csrf": rcsrf, "username": "evil", "role": "admin",
                                                          "password": "x" * 12, "password2": "x" * 12})
        self.assertEqual(st, 403)
        self.assertIsNone(self.conn.execute("SELECT 1 FROM users WHERE username='evil'").fetchone())
        st, _, _ = self.req("GET", "/day", rc)
        self.assertEqual(st, 200)
        ac, acsrf = self.login("admin", "correct-horse")
        st, h, body = self.req("GET", "/admin/backup/download", ac)
        self.assertEqual(st, 200)
        st, _, _ = self.req("POST", "/admin/staff", ac, {"username": "x2", "role": "admin", "password": "x" * 12, "password2": "x" * 12})
        self.assertEqual(st, 400)   # missing CSRF token

    def raw(self, data):
        import socket
        s = socket.create_connection(("127.0.0.1", self.port), 5)
        s.sendall(data)
        out = s.recv(200)
        s.close()
        return out.split(b"\r\n")[0]

    def test_bad_content_length_rejected(self):
        for v in (b"-1", b"abc", b"+5"):
            line = self.raw(b"POST /login HTTP/1.1\r\nHost: x\r\nContent-Length: " + v + b"\r\n\r\n")
            self.assertIn(b" 400 ", line, v)

    def test_password_change_ends_other_sessions(self):
        c1, csrf1 = self.login("rec", "receptionist1")
        c2, _ = self.login("rec", "receptionist1")
        st, _, _ = self.req("POST", "/password", c1, {"_csrf": csrf1, "current": "receptionist1",
                                                      "password": "receptionist2", "password2": "receptionist2"})
        self.assertEqual(st, 303)
        self.assertEqual(self.req("GET", "/day", c1)[0], 200)
        st, h, _ = self.req("GET", "/day", c2)
        self.assertEqual((st, h.get("Location")), (303, "/login"))

    def test_health(self):
        st, _, body = self.req("GET", "/health")
        self.assertEqual((st, body), (200, "ok\n"))
        self.server.app.db_path = os.path.join(self.dir, "missing", "frontdesk.db")
        self.assertEqual(self.req("GET", "/health")[0], 503)

    def test_lockout(self):
        for _ in range(5):
            with self.assertRaises(D.ValidationError):
                D.authenticate(self.conn, "rec", "wrong-password", now=T0)
        with self.assertRaises(D.ValidationError) as cm:
            D.authenticate(self.conn, "rec", "receptionist1", now=T0 + dt.timedelta(minutes=5))
        self.assertIn("locked", str(cm.exception))
        D.authenticate(self.conn, "rec", "receptionist1", now=T0 + dt.timedelta(minutes=16))

    def test_last_admin(self):
        with self.assertRaises(D.ValidationError):
            D.set_user_active(self.conn, self.admin, self.admin["id"], False)

    def test_export_csv_http(self):
        self.book(date="2026-12-01", now=D.utcnow() if D.utcnow() > T0 else T0, confirm=True)
        rc, _ = self.login("rec", "receptionist1")
        st, h, body = self.req("GET", "/export?from=2026-12-01&to=2026-12-01&download=1", rc)
        self.assertEqual(st, 200)
        rows = list(csv.reader(io.StringIO(body.lstrip("﻿"))))
        self.assertEqual(rows[0], D.CSV_HEADER)
        self.assertEqual(len(rows), 2)


if __name__ == "__main__":
    unittest.main()
