"""Thin helpers over FrontDesk Book's real HTTP interface, dispatched in process, with an injected clock.

The clock: every request reads `frontdesk.domain.utcnow()` (Req.now) and the reminder job calls
`process_due(conn, send)` which also falls back to `utcnow()`. We replace that one function.
"""
import os as _os
# These helpers find the repository from their own location. They live in
# tests/acceptance/_helpers/; paths are computed as if they sat one level below
# the repository root.
_HERE = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))), '_helpers', 'driver.py')
import datetime as dt
import os
import re
import sys
import tempfile
import urllib.parse
import html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(_HERE)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from frontdesk import config, db, domain as D, web, mailer  # noqa: E402
from frontdesk.app import App  # noqa: E402

UTC = dt.timezone.utc
TZ = "Europe/London"
PW = "correct-horse-1"


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t.replace(microsecond=0)

    def set(self, t):
        self.t = t

    def advance(self, **kw):
        self.t = self.t + dt.timedelta(**kw)


class Resp:
    def __init__(self, status, headers, body):
        self.status, self.headers, self.body = status, headers, body
        self.text = body.decode("utf-8", "replace") if isinstance(body, bytes) else body

    @property
    def location(self):
        return self.headers.get("Location")

    def __repr__(self):
        return "<Resp %s %s>" % (self.status, self.location or self.text[:200])


class Client:
    def __init__(self, sysm):
        self.sys = sysm
        self.cookies = {}
        self.creds = None

    def _cookie_header(self):
        return "; ".join("%s=%s" % kv for kv in self.cookies.items())

    def req(self, method, path, form=None, follow=True):
        body = b""
        headers = {"Cookie": self._cookie_header()}
        if form is not None:
            body = urllib.parse.urlencode(form, doseq=True).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            headers["Content-Length"] = str(len(body))
        st, hd, out = web.dispatch(self.sys.app, method, path, headers, body)
        sc = hd.get("Set-Cookie")
        if sc:
            k, v = sc.split(";")[0].split("=", 1)
            self.cookies[k] = v
        r = Resp(st, hd, out)
        if follow and st in (302, 303) and r.location:
            if r.location == "/login" and self.creds and path != "/login" and not getattr(self, "_relog", False):
                self._relog = True
                try:
                    self.login(*self.creds)
                finally:
                    self._relog = False
                if method == "GET":
                    return self.req(method, path, form, follow)
            return self.req("GET", r.location, follow=True)
        return r

    def get(self, path, **q):
        if q:
            path += "?" + urllib.parse.urlencode(q, doseq=True)
        return self.req("GET", path)

    def csrf(self, path="/day"):
        r = self.req("GET", path)
        m = re.search(r'name="_csrf" value="([^"]+)"', r.text)
        if not m:
            r = self.req("GET", "/login")
            m = re.search(r'name="_csrf" value="([^"]+)"', r.text)
        return m.group(1)

    def post(self, path, form=None, follow=True, csrf_from=None):
        form = dict(form or {})
        form.setdefault("_csrf", self.csrf(csrf_from or "/day"))
        return self.req("POST", path, form, follow=follow)

    def login(self, username, password):
        self.creds = (username, password)
        return self.post("/login", {"username": username, "password": password}, csrf_from="/login")


class System:
    """A fresh install in a temp data dir, signed in as admin, with a controllable clock."""

    def __init__(self, now=None, setup=True, tz=TZ, monkeypatch=None):
        self.dir = tempfile.mkdtemp(prefix="fdverify-")
        os.environ["FRONTDESK_DATA_DIR"] = self.dir
        self.cfg = config.load(os.path.join(self.dir, "none.conf"))
        self.cfg["data_dir"] = self.dir
        db.migrate(self.dir, log=lambda *a: None)
        self.app = App(self.cfg)
        self.clock = Clock(now or dt.datetime(2026, 3, 2, 8, 0, tzinfo=UTC))  # Monday
        self._orig = D.utcnow
        if monkeypatch is not None:
            monkeypatch.setattr(D, "utcnow", self.clock)
        else:
            D.utcnow = self.clock
        self.conn = db.connect(self.app.db_path)
        self.admin = Client(self)
        self.sent = []
        self.smtp_down = False
        if setup:
            r = self.admin.post("/setup", {"clinic_name": "Test Clinic", "tz": tz, "username": "admin",
                                           "password": PW, "password2": PW}, csrf_from="/setup")
            assert r.status == 200, r
            self.admin.creds = ("admin", PW)

    def close(self):
        D.utcnow = self._orig
        self.conn.close()

    # ---- time helpers
    def local(self, date, hhmm):
        from zoneinfo import ZoneInfo
        y, m, d = map(int, date.split("-"))
        h, mi = map(int, hhmm.split(":"))
        return dt.datetime(y, m, d, h, mi, tzinfo=ZoneInfo(TZ)).astimezone(UTC)

    def set_local(self, date, hhmm):
        self.clock.set(self.local(date, hhmm))

    # ---- setup via the admin UI forms
    def add_practitioner(self, name="Dr A", hours=None):
        r = self.admin.post("/admin/practitioners", {"name": name, "title": "", "colour": "#88aaff"})
        pid = int(re.search(r"/admin/practitioners/(\d+)", r.text + str(r.headers)).group(1)) if "/admin/practitioners/" in r.text else None
        if pid is None:
            pid = self.conn.execute("SELECT id FROM practitioners WHERE name=? ORDER BY id DESC", (name,)).fetchone()[0]
        if hours is not None:
            self.set_hours(pid, hours)
        return pid

    def set_hours(self, pid, hours):
        form = {"day%d" % i: hours.get(i, "") for i in range(7)}
        return self.admin.post("/admin/practitioners/%d/hours" % pid, form)

    def add_type(self, name="Consult", duration=30):
        self.admin.post("/admin/types", {"name": name, "duration": duration})
        return self.conn.execute("SELECT id FROM appt_types WHERE name=? ORDER BY id DESC", (name,)).fetchone()[0]

    def add_patient(self, first="Ann", last="Lee", email="ann@example.com", phone="07700 900123", dob="", reminders=True,
                    force=True, client=None):
        form = {"first_name": first, "last_name": last, "email": email, "phone": phone, "dob": dob}
        if reminders:
            form["send_reminders"] = "1"
        if force:
            form["force"] = "1"
        r = (client or self.admin).post("/patients/new", form)
        row = self.conn.execute("SELECT id FROM patients WHERE first_name=? AND last_name=? ORDER BY id DESC", (first, last)).fetchone()
        return (row[0] if row else None), r

    def basic(self):
        """Two practitioners working every day 08:00-18:00, one type, two patients."""
        allday = {i: "08:00-18:00" for i in range(7)}
        self.pa = self.add_practitioner("Dr A", allday)
        self.pb = self.add_practitioner("Dr B", allday)
        self.ty = self.add_type("Consult", 30)
        self.p1, _ = self.add_patient("Ann", "Lee", "ann@example.com", "07700 900111")
        self.p2, _ = self.add_patient("Bob", "Ray", "bob@example.com", "07700 900222")
        return self

    # ---- appointments
    def book(self, date, time, dur=30, pr=None, pat=None, ty=None, note="", confirm=False, client=None):
        form = {"practitioner_id": pr or self.pa, "patient_id": pat or self.p1, "type_id": ty or self.ty,
                "date": date, "time": time, "duration": dur, "note": note}
        if confirm:
            form["confirm"] = "1"
        r = (client or self.admin).post("/appt/new", form, follow=False)
        aid = None
        if r.status == 303 and re.match(r"/appt/\d+$", r.location or ""):
            aid = int(r.location.rsplit("/", 1)[1])
            r = (client or self.admin).req("GET", r.location)
        return aid, r

    def appt(self, aid):
        return dict(D.get_appt(self.conn, aid))

    def version(self, aid):
        return self.appt(aid)["version"]

    def move(self, aid, date, time, dur=30, pr=None, version=None, confirm=False, client=None):
        a = self.appt(aid)
        form = {"date": date, "time": time, "duration": dur, "practitioner_id": pr or a["practitioner_id"],
                "version": a["version"] if version is None else version}
        if confirm:
            form["confirm"] = "1"
        return (client or self.admin).post("/appt/%d/move" % aid, form)

    def cancel(self, aid, reason="patient", text="", version=None, client=None):
        return (client or self.admin).post("/appt/%d/cancel" % aid, {"reason": reason, "text": text,
                                                                     "version": self.version(aid) if version is None else version})

    def status(self, aid, st, client=None):
        return (client or self.admin).post("/appt/%d/status" % aid, {"status": st, "version": self.version(aid)})

    def undo(self, aid, client=None):
        return (client or self.admin).post("/appt/%d/undo" % aid, {"version": self.version(aid)})

    def reminder(self, aid):
        r = D.current_reminder(self.conn, aid)
        return dict(r) if r else None

    def receptionist(self, name="rita"):
        self.admin.post("/admin/staff", {"username": name, "role": "receptionist", "password": PW, "password2": PW})
        c = Client(self)
        c.login(name, PW)
        c.post("/password", {"current": PW, "password": PW + "x", "password2": PW + "x"}, csrf_from="/password")
        c.creds = (name, PW + "x")
        return c

    def settings(self, **kv):
        cur = dict(D.all_settings(self.conn))
        cur.update({k.replace("__", "."): v for k, v in kv.items()})
        return self.admin.post("/admin/settings", cur)

    # ---- reminder job (the same call the background loop makes)
    def send_fn(self, to, subj, body, rt):
        if self.smtp_down:
            raise ConnectionRefusedError("Connection refused")
        self.sent.append({"to": to, "subject": subj, "body": body})

    def run_job(self):
        return D.process_due(self.conn, self.send_fn)

    def run_job_real(self):
        s = mailer.effective(self.conn, self.cfg)
        return D.process_due(self.conn, lambda to, subj, body, rt: mailer.send(s, self.dir, to, subj, body, rt))

    def restart(self):
        D.recover_interrupted(self.conn)
        return self.run_job()


def unescape(s):
    return html.unescape(s)
