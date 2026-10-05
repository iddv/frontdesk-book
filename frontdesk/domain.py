"""Business rules: time handling, validation, patients, booking, statuses, reminders, reports."""
import datetime as dt
import hashlib
import hmac
import json
import re
import secrets
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .db import tx

UTC = dt.timezone.utc
GRID = 5                     # minutes
MIN_DURATION, MAX_DURATION = 5, 480
DAY_START, DAY_END = 7 * 60, 20 * 60
DEFAULT_HOURS = [(wd, 9 * 60, 17 * 60) for wd in range(5)]
LATE_CANCEL_HOURS = 24
REMINDER_LEAD_HOURS = 24
IMMEDIATE_MIN_HOURS = 2      # booked inside the window: send now only if start is further away than this
CATCHUP_MIN_HOURS = 1        # job: still send a due reminder only if start is further away than this
RETRIES, RETRY_MINUTES = 3, 10
PASSWORD_MIN = 10
LOCK_AFTER, LOCK_MINUTES = 5, 15
SESSION_IDLE_HOURS = 8
NOTE_MAX = 200
NAME_MAX = 100
EXPORT_MAX_DAYS = 366

SETTINGS = {
    "booking.outside_hours": (("block", "warn"), "warn",
                              "Whether booking outside working hours or in time-off is refused or allowed after confirmation."),
    "booking.patient_overlap": (("block", "warn"), "warn",
                                "Whether a patient may hold two overlapping appointments with different practitioners."),
    "reminders.cancellation_email": (("on", "off"), "on",
                                     "Whether a patient with email gets a short email when their appointment is cancelled."),
    "patients.reminder_default": (("on", "off"), "on",
                                  "Whether “send reminders” starts ticked for new patients."),
}
STATUS_LABEL = {"booked": "Booked", "attended": "Attended", "no_show": "No-show", "cancelled": "Cancelled"}
CANCEL_REASONS = {"patient": "Patient cancelled", "clinic": "Clinic cancelled", "other": "Other"}
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ---------------------------------------------------------------- errors
class AppError(Exception):
    pass


class ValidationError(AppError):
    def __init__(self, errors):
        if isinstance(errors, str):
            errors = {"_": errors}
        self.errors = errors
        super().__init__("; ".join(errors.values()))


class Conflict(AppError):
    pass


class Stale(AppError):
    pass


class NotFound(AppError):
    pass


class NeedsConfirm(AppError):
    def __init__(self, warnings):
        self.warnings = warnings
        super().__init__("; ".join(str(w) for w in warnings))


# ---------------------------------------------------------------- time
def utcnow():
    return dt.datetime.now(UTC).replace(microsecond=0)


def to_s(d):
    return d.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


def from_s(s):
    return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC) if s else None


def tz_of(conn):
    row = conn.execute("SELECT tz FROM clinic WHERE id=1").fetchone()
    return ZoneInfo(row["tz"] if row else "UTC")


def parse_date(s, field="date"):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise ValidationError({field: "Enter a valid date (YYYY-MM-DD)."})


def parse_hhmm(s, field="time"):
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", s or "")
    if not m or int(m.group(1)) > 24 or int(m.group(2)) > 59 or (int(m.group(1)) == 24 and int(m.group(2))):
        raise ValidationError({field: "Enter a time as HH:MM."})
    return int(m.group(1)) * 60 + int(m.group(2))


def hhmm(minutes):
    return "%02d:%02d" % divmod(int(minutes), 60)


def local_to_utc(tz, d, minutes):
    naive = dt.datetime.combine(d, dt.time(0)) + dt.timedelta(minutes=minutes)
    aware = naive.replace(tzinfo=tz)
    back = aware.astimezone(UTC).astimezone(tz).replace(tzinfo=None)
    if back != naive:
        raise ValidationError({"time": "%s does not exist on %s because of the daylight-saving change." % (hhmm(minutes), d)})
    return aware.astimezone(UTC)


def day_bounds(tz, d):
    start = dt.datetime.combine(d, dt.time(0)).replace(tzinfo=tz).astimezone(UTC)
    end = dt.datetime.combine(d + dt.timedelta(days=1), dt.time(0)).replace(tzinfo=tz).astimezone(UTC)
    return start, end


def local(tz, s_or_dt):
    d = from_s(s_or_dt) if isinstance(s_or_dt, str) else s_or_dt
    return d.astimezone(tz)


def local_minutes(tz, s, ref_date):
    """Wall-clock minutes since ref_date midnight (can exceed 1440 for the next day)."""
    l = local(tz, s)
    return (l.date() - ref_date).days * 1440 + l.hour * 60 + l.minute


def fmt_dt(tz, s):
    l = local(tz, s)
    return "%s %d %s %s" % (l.strftime("%a"), l.day, l.strftime("%b"), l.strftime("%H:%M"))


def fmt_date(d):
    return "%s %d %s %d" % (d.strftime("%a"), d.day, d.strftime("%b"), d.year)


def floor_grid(now):
    return now.replace(second=0, microsecond=0, minute=now.minute - now.minute % GRID)


def machine_tz():
    import os
    tzname = os.environ.get("TZ", "")
    if not tzname:
        try:
            with open("/etc/timezone") as f:
                tzname = f.read().strip()
        except OSError:
            try:
                tzname = os.path.realpath("/etc/localtime").split("zoneinfo/", 1)[1]
            except (OSError, IndexError):
                tzname = ""
    try:
        ZoneInfo(tzname)
        return tzname
    except (ZoneInfoNotFoundError, ValueError):
        return "UTC"


# ---------------------------------------------------------------- passwords & settings
def hash_password(pw):
    salt = secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 240000)
    return "pbkdf2$240000$%s$%s" % (salt.hex(), h.hex())


def check_password(pw, stored):
    try:
        _, n, salt, h = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), int(n))
        return hmac.compare_digest(calc.hex(), h)
    except (ValueError, AttributeError):
        return False


def validate_password(pw, pw2):
    if len(pw or "") < PASSWORD_MIN:
        raise ValidationError({"password": "Password must be at least %d characters." % PASSWORD_MIN})
    if pw != pw2:
        raise ValidationError({"password2": "The two passwords do not match."})


def get_setting(conn, key):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else SETTINGS[key][1]


def all_settings(conn):
    return {k: get_setting(conn, k) for k in SETTINGS}


def audit(conn, user_id, kind, detail, now=None):
    conn.execute("INSERT INTO audit_log(at,user_id,kind,detail) VALUES(?,?,?,?)",
                 (to_s(now or utcnow()), user_id, kind, detail if isinstance(detail, str) else json.dumps(detail)))


def set_settings(conn, user, values, now=None):
    errors = {}
    for k, v in values.items():
        if k not in SETTINGS or v not in SETTINGS[k][0]:
            errors[k] = "Choose one of: %s." % ", ".join(SETTINGS.get(k, ((),))[0])
    if errors:
        raise ValidationError(errors)
    with tx(conn):
        for k, v in values.items():
            old = get_setting(conn, k)
            if old != v:
                conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (k, v))
                audit(conn, user["id"], "setting", {"key": k, "old": old, "new": v}, now)


# ---------------------------------------------------------------- generic helpers
def username_of(conn, uid):
    if uid is None:
        return "system"
    r = conn.execute("SELECT username FROM users WHERE id=?", (uid,)).fetchone()
    return r["username"] if r else "unknown"


def _bump(conn, table, rid, version, sets, params, user_id=None, now=None):
    """Optimistic-lock update. Raises Stale when the row changed since it was read."""
    cur = conn.execute("UPDATE %s SET %s, version=version+1 WHERE id=? AND version=?" % (table, sets),
                       list(params) + [rid, int(version)])
    if cur.rowcount == 0:
        row = conn.execute("SELECT * FROM %s WHERE id=?" % table, (rid,)).fetchone()
        if row is None:
            raise NotFound("That record no longer exists.")
        who = username_of(conn, row["updated_by"]) if "updated_by" in row.keys() else "someone else"
        raise Stale("This record was changed by %s; reload." % who)


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[0-9 \-]+$")


def clean_phone(phone):
    phone = (phone or "").strip()
    if not phone:
        return "", ""
    digits = re.sub(r"\D", "", phone)
    if not PHONE_RE.match(phone) or not 6 <= len(digits) <= 20:
        raise ValidationError({"phone": "Phone must have 6–20 digits, an optional leading +, spaces and dashes."})
    return phone, digits


def clean_email(email, field="email"):
    email = (email or "").strip()
    if email and (not EMAIL_RE.match(email) or len(email) > 254):
        raise ValidationError({field: "Enter a valid email address."})
    return email


# ---------------------------------------------------------------- clinic & staff
def create_first_admin(conn, clinic_name, tzname, username, pw, pw2, now=None):
    now = now or utcnow()
    errors = {}
    if not (clinic_name or "").strip():
        errors["clinic_name"] = "Enter the clinic name."
    try:
        ZoneInfo((tzname or "").strip())
    except (ZoneInfoNotFoundError, ValueError):
        errors["tz"] = "Choose a valid time zone, e.g. Europe/London."
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,40}", username or ""):
        errors["username"] = "Username: 3–40 letters, digits, dot, dash or underscore."
    try:
        validate_password(pw, pw2)
    except ValidationError as e:
        errors.update(e.errors)
    if errors:
        raise ValidationError(errors)
    with tx(conn):
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            raise Conflict("The clinic is already set up.")
        conn.execute("INSERT OR REPLACE INTO clinic(id,name,tz) VALUES(1,?,?)", (clinic_name.strip(), tzname.strip()))
        uid = conn.execute("INSERT INTO users(username,role,pw_hash,created_at) VALUES(?,?,?,?)",
                           (username, "admin", hash_password(pw), to_s(now))).lastrowid
        audit(conn, uid, "staff", "created first admin %s" % username, now)
    return uid


def update_clinic(conn, user, f, now=None):
    errors = {}
    name = (f.get("name") or "").strip()
    if not name:
        errors["name"] = "Enter the clinic name."
    try:
        _, _ = clean_phone(f.get("phone"))
    except ValidationError as e:
        errors.update(e.errors)
    try:
        reply_to = clean_email(f.get("reply_to"), "reply_to")
    except ValidationError as e:
        errors.update(e.errors)
        reply_to = ""
    if errors:
        raise ValidationError(errors)
    with tx(conn):
        _bump(conn, "clinic", 1, f.get("version", 0), "name=?, address=?, phone=?, reply_to=?, updated_by=?, updated_at=?",
              (name, (f.get("address") or "").strip()[:300], (f.get("phone") or "").strip(), reply_to, user["id"], to_s(now or utcnow())))
        audit(conn, user["id"], "clinic", "updated clinic details", now)


def update_email_settings(conn, user, f, now=None):
    errors = {}
    mode = f.get("email_mode")
    if mode not in ("smtp", "log"):
        errors["email_mode"] = "Choose smtp or log."
    tls = f.get("smtp_tls")
    if tls not in ("none", "starttls", "ssl"):
        errors["smtp_tls"] = "Choose none, starttls or ssl."
    try:
        port = int(f.get("smtp_port") or 0)
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        errors["smtp_port"] = "Enter a port between 1 and 65535."
        port = 0
    try:
        sender = clean_email(f.get("smtp_from"), "smtp_from")
    except ValidationError as e:
        errors.update(e.errors)
        sender = ""
    if mode == "smtp":
        if not (f.get("smtp_host") or "").strip():
            errors["smtp_host"] = "Enter the mail server host."
        if not sender:
            errors["smtp_from"] = "Enter the from address."
    if errors:
        raise ValidationError(errors)
    sets = "email_mode=?, smtp_host=?, smtp_port=?, smtp_tls=?, smtp_user=?, smtp_from=?, updated_by=?, updated_at=?"
    params = [mode, f["smtp_host"].strip(), port, tls, (f.get("smtp_user") or "").strip(), sender, user["id"], to_s(now or utcnow())]
    if f.get("smtp_password"):           # blank keeps the stored password
        sets += ", smtp_password=?"
        params.append(f["smtp_password"])
    with tx(conn):
        _bump(conn, "clinic", 1, f.get("version", 0), sets, params)
        audit(conn, user["id"], "email", "updated email settings (mode %s, host %s)" % (mode, f["smtp_host"].strip()), now)


def create_user(conn, actor, username, role, pw, pw2, now=None):
    now = now or utcnow()
    if not re.fullmatch(r"[A-Za-z0-9._-]{3,40}", username or ""):
        raise ValidationError({"username": "Username: 3–40 letters, digits, dot, dash or underscore."})
    if role not in ("admin", "receptionist"):
        raise ValidationError({"role": "Choose admin or receptionist."})
    validate_password(pw, pw2)
    with tx(conn):
        if conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            raise ValidationError({"username": "That username is taken."})
        uid = conn.execute("INSERT INTO users(username,role,pw_hash,must_change,created_at) VALUES(?,?,?,1,?)",
                           (username, role, hash_password(pw), to_s(now))).lastrowid
        audit(conn, actor["id"], "staff", "created %s account %s" % (role, username), now)
    return uid


def reset_password(conn, actor, uid, now=None):
    temp = secrets.token_urlsafe(9)
    with tx(conn):
        u = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not u:
            raise NotFound("No such account.")
        conn.execute("UPDATE users SET pw_hash=?, must_change=1, failed_count=0, locked_until=NULL, version=version+1 WHERE id=?",
                     (hash_password(temp), uid))
        conn.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
        audit(conn, actor["id"], "staff", "reset password for %s" % u["username"], now)
    return temp


def set_user_active(conn, actor, uid, active, now=None):
    with tx(conn):
        u = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not u:
            raise NotFound("No such account.")
        if not active and u["role"] == "admin":
            n = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1 AND id!=?", (uid,)).fetchone()[0]
            if n == 0:
                raise ValidationError("You cannot deactivate the last active admin.")
        conn.execute("UPDATE users SET active=?, version=version+1 WHERE id=?", (1 if active else 0, uid))
        if not active:
            conn.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
        audit(conn, actor["id"], "staff", "%s account %s" % ("reactivated" if active else "deactivated", u["username"]), now)


def set_user_role(conn, actor, uid, role, now=None):
    if role not in ("admin", "receptionist"):
        raise ValidationError({"role": "Choose admin or receptionist."})
    with tx(conn):
        u = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not u:
            raise NotFound("No such account.")
        if u["role"] == "admin" and role != "admin" and u["active"]:
            if not conn.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1 AND id!=?", (uid,)).fetchone()[0]:
                raise ValidationError("You cannot remove the last active admin.")
        conn.execute("UPDATE users SET role=?, version=version+1 WHERE id=?", (role, uid))
        audit(conn, actor["id"], "staff", "changed role of %s to %s" % (u["username"], role), now)


def change_own_password(conn, user, current, pw, pw2, now=None, keep_token=None):
    """Changes the user's password and ends all their other sessions (all but keep_token)."""
    u = conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
    if not check_password(current or "", u["pw_hash"]):
        raise ValidationError({"current": "Current password is not correct."})
    validate_password(pw, pw2)
    if pw == current:
        raise ValidationError({"password": "Choose a new password different from the current one."})
    with tx(conn):
        conn.execute("UPDATE users SET pw_hash=?, must_change=0, version=version+1 WHERE id=?", (hash_password(pw), u["id"]))
        conn.execute("DELETE FROM sessions WHERE user_id=? AND token IS NOT ?", (u["id"], keep_token))
        audit(conn, u["id"], "staff", "%s changed own password" % u["username"], now)


def authenticate(conn, username, pw, now=None):
    """Returns the user row or raises ValidationError with a generic message."""
    now = now or utcnow()
    generic = ValidationError("Wrong username or password.")
    with tx(conn):
        u = conn.execute("SELECT * FROM users WHERE username=?", (username or "",)).fetchone()
        if not u or not u["active"]:
            check_password(pw or "", "pbkdf2$240000$00$00")  # similar timing
            raise generic
        if u["locked_until"] and from_s(u["locked_until"]) > now:
            raise ValidationError("This account is locked after too many failed sign-ins. Try again after %s."
                                  % fmt_dt(tz_of(conn), u["locked_until"])[-5:])
        if not check_password(pw or "", u["pw_hash"]):
            n = u["failed_count"] + 1
            locked = to_s(now + dt.timedelta(minutes=LOCK_MINUTES)) if n >= LOCK_AFTER else None
            conn.execute("UPDATE users SET failed_count=?, locked_until=? WHERE id=?", (0 if locked else n, locked, u["id"]))
            if locked:
                audit(conn, None, "staff", "account %s locked after %d failed sign-ins" % (u["username"], LOCK_AFTER), now)
        else:
            conn.execute("UPDATE users SET failed_count=0, locked_until=NULL WHERE id=?", (u["id"],))
            return u
    if locked:
        raise ValidationError("Too many failed sign-ins: the account is locked for %d minutes." % LOCK_MINUTES)
    raise generic


# ---------------------------------------------------------------- practitioners, hours, types
COLOUR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def save_practitioner(conn, user, f, pid=None, now=None):
    now = now or utcnow()
    name = (f.get("name") or "").strip()
    errors = {}
    if not name or len(name) > NAME_MAX:
        errors["name"] = "Enter a display name (up to %d characters)." % NAME_MAX
    colour = f.get("colour") or "#4a90d9"
    if not COLOUR_RE.match(colour):
        errors["colour"] = "Choose a colour."
    if errors:
        raise ValidationError(errors)
    title = (f.get("title") or "").strip()[:60]
    with tx(conn):
        if pid is None:
            pid = conn.execute("INSERT INTO practitioners(name,title,colour,created_at) VALUES(?,?,?,?)",
                               (name, title, colour, to_s(now))).lastrowid
            conn.executemany("INSERT INTO practitioner_hours(practitioner_id,weekday,start_min,end_min) VALUES(?,?,?,?)",
                             [(pid, wd, s, e) for wd, s, e in DEFAULT_HOURS])
            audit(conn, user["id"], "practitioner", "added practitioner %s" % name, now)
        else:
            _bump(conn, "practitioners", pid, f.get("version", 0), "name=?, title=?, colour=?", (name, title, colour))
            audit(conn, user["id"], "practitioner", "edited practitioner %s" % name, now)
    return pid


def parse_hours(text_by_day):
    """{weekday: 'HH:MM-HH:MM, HH:MM-HH:MM'} -> list of (wd, s, e); rejects overlaps and reversed ranges."""
    out, errors = [], {}
    for wd in range(7):
        raw = (text_by_day.get(wd) or "").strip()
        ranges = []
        for part in [p.strip() for p in raw.split(",") if p.strip()]:
            m = re.fullmatch(r"(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})", part)
            if not m:
                errors["day%d" % wd] = "%s: write ranges like 09:00-12:30, 13:30-17:00." % WEEKDAYS[wd]
                break
            try:
                s, e = parse_hhmm(m.group(1)), parse_hhmm(m.group(2))
            except ValidationError:
                errors["day%d" % wd] = "%s: %s is not a valid time range." % (WEEKDAYS[wd], part)
                break
            if s % GRID or e % GRID:
                errors["day%d" % wd] = "%s: times must be on the %d-minute grid." % (WEEKDAYS[wd], GRID)
                break
            if e <= s:
                errors["day%d" % wd] = "%s: %s ends before it starts." % (WEEKDAYS[wd], part)
                break
            ranges.append((s, e))
        ranges.sort()
        for (s1, e1), (s2, e2) in zip(ranges, ranges[1:]):
            if s2 < e1:
                errors["day%d" % wd] = "%s: %s-%s overlaps %s-%s." % (WEEKDAYS[wd], hhmm(s1), hhmm(e1), hhmm(s2), hhmm(e2))
        out += [(wd, s, e) for s, e in ranges]
    if errors:
        raise ValidationError(errors)
    return out


def set_hours(conn, user, pid, text_by_day, now=None):
    hours = parse_hours(text_by_day)
    with tx(conn):
        p = conn.execute("SELECT * FROM practitioners WHERE id=?", (pid,)).fetchone()
        if not p:
            raise NotFound("No such practitioner.")
        conn.execute("DELETE FROM practitioner_hours WHERE practitioner_id=?", (pid,))
        conn.executemany("INSERT INTO practitioner_hours(practitioner_id,weekday,start_min,end_min) VALUES(?,?,?,?)",
                         [(pid, wd, s, e) for wd, s, e in hours])
        audit(conn, user["id"], "practitioner", "set working hours for %s" % p["name"], now)


def hours_for(conn, pid):
    by = {wd: [] for wd in range(7)}
    for r in conn.execute("SELECT * FROM practitioner_hours WHERE practitioner_id=? ORDER BY weekday,start_min", (pid,)):
        by[r["weekday"]].append((r["start_min"], r["end_min"]))
    return by


def timeoff_for(conn, pid, d1, d2):
    return conn.execute("SELECT * FROM timeoff WHERE practitioner_id=? AND start_date<=? AND end_date>=? ORDER BY start_date",
                        (pid, d2.isoformat(), d1.isoformat())).fetchall()


def appts_affected_by_timeoff(conn, pid, d1, d2, s_min, e_min):
    tz = tz_of(conn)
    start, _ = day_bounds(tz, d1)
    _, end = day_bounds(tz, d2)
    rows = conn.execute("""SELECT a.*, p.first_name, p.last_name FROM appointments a JOIN patients p ON p.id=a.patient_id
                           WHERE a.practitioner_id=? AND a.status='booked' AND a.start_utc<? AND a.end_utc>? ORDER BY a.start_utc""",
                        (pid, to_s(end), to_s(start))).fetchall()
    if s_min is None:
        return rows
    out = []
    for a in rows:
        d = local(tz, a["start_utc"]).date()
        s = local_minutes(tz, a["start_utc"], d)
        e = local_minutes(tz, a["end_utc"], d)
        if s < e_min and e > s_min:
            out.append(a)
    return out


def add_timeoff(conn, user, pid, f, confirm=False, now=None):
    errors = {}
    try:
        d1 = parse_date(f.get("start_date"), "start_date")
        d2 = parse_date(f.get("end_date") or f.get("start_date"), "end_date")
        if d2 < d1:
            errors["end_date"] = "End date is before start date."
    except ValidationError as e:
        errors.update(e.errors)
    s_min = e_min = None
    if f.get("start_time") or f.get("end_time"):
        try:
            s_min, e_min = parse_hhmm(f.get("start_time"), "start_time"), parse_hhmm(f.get("end_time"), "end_time")
            if e_min <= s_min:
                errors["end_time"] = "End time is before start time."
        except ValidationError as e:
            errors.update(e.errors)
    label = (f.get("label") or "").strip()[:40]
    if not label:
        errors["label"] = "Enter a short label, e.g. Leave."
    if errors:
        raise ValidationError(errors)
    with tx(conn):
        affected = appts_affected_by_timeoff(conn, pid, d1, d2, s_min, e_min)
        if affected and not confirm:
            tz = tz_of(conn)
            raise NeedsConfirm(["%s %s %s" % (fmt_dt(tz, a["start_utc"]), a["first_name"], a["last_name"]) for a in affected])
        conn.execute("INSERT INTO timeoff(practitioner_id,start_date,end_date,start_min,end_min,label,created_by,created_at) "
                     "VALUES(?,?,?,?,?,?,?,?)", (pid, d1.isoformat(), d2.isoformat(), s_min, e_min, label, user["id"], to_s(now or utcnow())))
        audit(conn, user["id"], "practitioner", "added time-off %s %s..%s for practitioner %d" % (label, d1, d2, pid), now)


def delete_timeoff(conn, user, tid, now=None):
    with tx(conn):
        conn.execute("DELETE FROM timeoff WHERE id=?", (tid,))
        audit(conn, user["id"], "practitioner", "removed time-off %d" % tid, now)


def archive_practitioner(conn, user, pid, archived, now=None):
    now = now or utcnow()
    with tx(conn):
        if archived:
            fut = conn.execute("""SELECT a.*, p.first_name, p.last_name FROM appointments a JOIN patients p ON p.id=a.patient_id
                                  WHERE a.practitioner_id=? AND a.status='booked' AND a.end_utc>? ORDER BY a.start_utc""",
                               (pid, to_s(now))).fetchall()
            if fut:
                tz = tz_of(conn)
                raise NeedsConfirm(["%s %s %s" % (fmt_dt(tz, a["start_utc"]), a["first_name"], a["last_name"]) for a in fut])
        conn.execute("UPDATE practitioners SET archived=?, version=version+1 WHERE id=?", (1 if archived else 0, pid))
        audit(conn, user["id"], "practitioner", "%s practitioner %d" % ("archived" if archived else "restored", pid), now)


def save_type(conn, user, f, tid=None, now=None):
    name = (f.get("name") or "").strip()
    errors = {}
    if not name or len(name) > NAME_MAX:
        errors["name"] = "Enter a name (up to %d characters)." % NAME_MAX
    try:
        dur = int(f.get("duration") or 0)
        if not MIN_DURATION <= dur <= MAX_DURATION or dur % GRID:
            raise ValueError
    except ValueError:
        errors["duration"] = "Duration must be %d–%d minutes in %d-minute steps." % (MIN_DURATION, MAX_DURATION, GRID)
        dur = 0
    if errors:
        raise ValidationError(errors)
    with tx(conn):
        if tid is None:
            tid = conn.execute("INSERT INTO appt_types(name,duration) VALUES(?,?)", (name, dur)).lastrowid
        else:
            _bump(conn, "appt_types", tid, f.get("version", 0), "name=?, duration=?", (name, dur))
        audit(conn, user["id"], "type", "saved appointment type %s (%d min)" % (name, dur), now)
    return tid


def archive_type(conn, user, tid, archived, now=None):
    with tx(conn):
        conn.execute("UPDATE appt_types SET archived=?, version=version+1 WHERE id=?", (1 if archived else 0, tid))
        audit(conn, user["id"], "type", "%s appointment type %d" % ("archived" if archived else "restored", tid), now)


def delete_type(conn, user, tid, now=None):
    with tx(conn):
        if conn.execute("SELECT 1 FROM appointments WHERE type_id=? LIMIT 1", (tid,)).fetchone():
            raise ValidationError("This type has been used by appointments; archive it instead.")
        conn.execute("DELETE FROM appt_types WHERE id=?", (tid,))
        audit(conn, user["id"], "type", "deleted unused appointment type %d" % tid, now)


# ---------------------------------------------------------------- patients
def clean_patient(conn, f, now=None):
    errors = {}
    out = {}
    for k, label in (("first_name", "First name"), ("last_name", "Last name")):
        v = (f.get(k) or "").strip()
        if not v:
            errors[k] = "%s is required." % label
        elif len(v) > NAME_MAX:
            errors[k] = "%s must be at most %d characters." % (label, NAME_MAX)
        out[k] = v
    out["dob"] = None
    if (f.get("dob") or "").strip():
        try:
            d = parse_date(f["dob"], "dob")
            today = local(tz_of(conn), now or utcnow()).date()
            if d > today:
                errors["dob"] = "Date of birth cannot be in the future."
            elif d.year < 1900:
                errors["dob"] = "Enter a valid date of birth."
            out["dob"] = d.isoformat()
        except ValidationError as e:
            errors.update(e.errors)
    try:
        out["phone"], out["phone_digits"] = clean_phone(f.get("phone"))
    except ValidationError as e:
        errors.update(e.errors)
    try:
        out["email"] = clean_email(f.get("email"))
    except ValidationError as e:
        errors.update(e.errors)
    if not errors and not out["phone"] and not out["email"]:
        errors["phone"] = "Enter a phone number or an email address (at least one is required)."
    out["send_reminders"] = 1 if f.get("send_reminders") in ("1", "on", True, 1) else 0
    if errors:
        raise ValidationError(errors)
    return out


def find_duplicates(conn, p, exclude_id=None):
    conds, params = [], []
    if p.get("dob"):
        conds.append("(lower(first_name)=lower(?) AND lower(last_name)=lower(?) AND dob=?)")
        params += [p["first_name"], p["last_name"], p["dob"]]
    if p.get("phone_digits"):
        conds.append("phone_digits=?")
        params.append(p["phone_digits"])
    if p.get("email"):
        conds.append("lower(email)=lower(?)")
        params.append(p["email"])
    if not conds:
        return []
    return conn.execute("SELECT * FROM patients WHERE (%s) AND id!=? ORDER BY last_name, first_name" % " OR ".join(conds),
                        params + [exclude_id or 0]).fetchall()


def create_patient(conn, user, f, force=False, now=None):
    now = now or utcnow()
    p = clean_patient(conn, f, now)
    with tx(conn):
        dups = find_duplicates(conn, p)
        if dups and not force:
            raise NeedsConfirm(dups)
        return conn.execute("""INSERT INTO patients(first_name,last_name,dob,phone,phone_digits,email,send_reminders,created_at,updated_at,updated_by)
                               VALUES(?,?,?,?,?,?,?,?,?,?)""",
                            (p["first_name"], p["last_name"], p["dob"], p["phone"], p["phone_digits"], p["email"],
                             p["send_reminders"], to_s(now), to_s(now), user["id"])).lastrowid


def get_patient(conn, pid):
    p = conn.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    if not p:
        raise NotFound("Patient not found.")
    return p


def update_patient(conn, user, pid, f, now=None):
    now = now or utcnow()
    p = clean_patient(conn, f, now)
    with tx(conn):
        cur = get_patient(conn, pid)
        if cur["archived"]:
            raise NotFound("This patient has been archived by another user.")
        _bump(conn, "patients", pid, f.get("version", 0),
              "first_name=?, last_name=?, dob=?, phone=?, phone_digits=?, email=?, send_reminders=?, updated_at=?, updated_by=?",
              (p["first_name"], p["last_name"], p["dob"], p["phone"], p["phone_digits"], p["email"], p["send_reminders"],
               to_s(now), user["id"]))
        if (cur["email"], cur["send_reminders"]) != (p["email"], p["send_reminders"]):
            # contact preferences changed: re-evaluate reminders of future booked appointments not yet sent
            for a in conn.execute("SELECT id FROM appointments WHERE patient_id=? AND status='booked' AND start_utc>?",
                                  (pid, to_s(now))).fetchall():
                st = current_reminder(conn, a["id"])
                if st is None or st["state"] in ("pending", "skipped", "failed"):
                    schedule_reminder(conn, a["id"], now, user["id"], force_new=True)


def archive_patient(conn, user, pid, archived, version, now=None):
    now = now or utcnow()
    with tx(conn):
        get_patient(conn, pid)
        if archived:
            fut = conn.execute("""SELECT a.*, pr.name AS pr_name FROM appointments a JOIN practitioners pr ON pr.id=a.practitioner_id
                                  WHERE a.patient_id=? AND a.status='booked' AND a.start_utc>? ORDER BY a.start_utc""",
                               (pid, to_s(now))).fetchall()
            if fut:
                tz = tz_of(conn)
                raise NeedsConfirm(["%s with %s" % (fmt_dt(tz, a["start_utc"]), a["pr_name"]) for a in fut])
        _bump(conn, "patients", pid, version, "archived=?, updated_at=?, updated_by=?", (1 if archived else 0, to_s(now), user["id"]))


def search_patients(conn, q, include_archived=False, now=None, limit=100):
    now = now or utcnow()
    q = (q or "").strip()
    conds, params = [], []
    if q:
        sub = ["(first_name || ' ' || last_name) LIKE ? ESCAPE '\\'", "(last_name || ' ' || first_name) LIKE ? ESCAPE '\\'",
               "lower(email) LIKE lower(?) ESCAPE '\\'"]
        like = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        params += [like, like, like]
        digits = re.sub(r"\D", "", q)
        if len(digits) >= 3 and re.fullmatch(r"[+\d \-]+", q):
            sub.append("phone_digits LIKE ?")
            params.append("%" + digits + "%")
        try:
            params.append(parse_date(q).isoformat())
            sub.append("dob=?")
        except ValidationError:
            pass
        conds.append("(" + " OR ".join(sub) + ")")
    if not include_archived:
        conds.append("archived=0")
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    return conn.execute("""SELECT p.*, (SELECT MIN(start_utc) FROM appointments a WHERE a.patient_id=p.id AND a.status='booked'
                                       AND a.start_utc>=?) AS next_start
                           FROM patients p %s ORDER BY last_name COLLATE NOCASE, first_name COLLATE NOCASE LIMIT ?""" % where,
                        [to_s(now)] + params + [limit]).fetchall()


# ---------------------------------------------------------------- appointments
APPT_SELECT = """SELECT a.*, p.first_name, p.last_name, p.phone, p.email, p.send_reminders, p.archived AS patient_archived,
                 pr.name AS pr_name, pr.colour AS pr_colour, t.name AS type_name
                 FROM appointments a JOIN patients p ON p.id=a.patient_id JOIN practitioners pr ON pr.id=a.practitioner_id
                 JOIN appt_types t ON t.id=a.type_id"""


def get_appt(conn, aid):
    a = conn.execute(APPT_SELECT + " WHERE a.id=?", (aid,)).fetchone()
    if not a:
        raise NotFound("Appointment not found.")
    return a


def history(conn, aid, action, user_id, now, details=None):
    conn.execute("INSERT INTO appt_history(appointment_id,at,user_id,action,details) VALUES(?,?,?,?,?)",
                 (aid, to_s(now), user_id, action, json.dumps(details or {})))


def outside_hours_reason(conn, tz, pid, start_s, end_s):
    d = local(tz, start_s).date()
    s = local_minutes(tz, start_s, d)
    e = local_minutes(tz, end_s, d)
    for t in timeoff_for(conn, pid, d, d):
        if t["start_min"] is None or (s < t["end_min"] and e > t["start_min"]):
            return "in time-off (%s)" % t["label"]
    for hs, he in hours_for(conn, pid)[d.weekday()]:
        if hs <= s and e <= he:
            return None
    return "outside working hours"


def overlap_conflict(conn, tz, pid, start_s, end_s, exclude_id):
    c = conn.execute("""SELECT a.start_utc, a.end_utc, p.first_name, p.last_name FROM appointments a JOIN patients p ON p.id=a.patient_id
                        WHERE a.practitioner_id=? AND a.status!='cancelled' AND a.start_utc<? AND a.end_utc>? AND a.id!=? LIMIT 1""",
                     (pid, end_s, start_s, exclude_id or 0)).fetchone()
    if c:
        return "Conflicts with %s %s %s–%s" % (c["first_name"], c["last_name"], local(tz, c["start_utc"]).strftime("%H:%M"),
                                                    local(tz, c["end_utc"]).strftime("%H:%M"))
    return None


def patient_overlap(conn, tz, patient_id, start_s, end_s, exclude_id):
    c = conn.execute("""SELECT a.start_utc, a.end_utc, pr.name FROM appointments a JOIN practitioners pr ON pr.id=a.practitioner_id
                        WHERE a.patient_id=? AND a.status!='cancelled' AND a.start_utc<? AND a.end_utc>? AND a.id!=? LIMIT 1""",
                     (patient_id, end_s, start_s, exclude_id or 0)).fetchone()
    if c:
        return "The patient already has an appointment with %s %s–%s" % (
            c["name"], local(tz, c["start_utc"]).strftime("%H:%M"), local(tz, c["end_utc"]).strftime("%H:%M"))
    return None


def check_slot(conn, tz, pid, patient_id, start, end, exclude_id, now, confirm):
    """All F4 checks. Must run inside the same transaction as the save."""
    if start < floor_grid(now):
        raise ValidationError({"time": "The start time is in the past."})
    start_s, end_s = to_s(start), to_s(end)
    msg = overlap_conflict(conn, tz, pid, start_s, end_s, exclude_id)
    if msg:
        raise Conflict(msg)
    warnings = []
    why = outside_hours_reason(conn, tz, pid, start_s, end_s)
    if why:
        if get_setting(conn, "booking.outside_hours") == "block":
            raise ValidationError({"time": "This time is %s." % why})
        warnings.append("This time is %s." % why)
    po = patient_overlap(conn, tz, patient_id, start_s, end_s, exclude_id)
    if po:
        if get_setting(conn, "booking.patient_overlap") == "block":
            raise Conflict(po + ".")
        warnings.append(po + ".")
    if warnings and not confirm:
        raise NeedsConfirm(warnings)


def _parse_when(conn, tz, f):
    errors = {}
    d = minutes = dur = None
    try:
        d = parse_date(f.get("date"), "date")
    except ValidationError as e:
        errors.update(e.errors)
    try:
        minutes = parse_hhmm(f.get("time"), "time")
        if minutes % GRID:
            errors["time"] = "Times must be on the %d-minute grid." % GRID
    except ValidationError as e:
        errors.update(e.errors)
    try:
        dur = int(f.get("duration") or 0)
        if not MIN_DURATION <= dur <= MAX_DURATION or dur % GRID:
            raise ValueError
    except ValueError:
        errors["duration"] = "Duration must be %d–%d minutes in %d-minute steps." % (MIN_DURATION, MAX_DURATION, GRID)
    if errors:
        raise ValidationError(errors)
    start = local_to_utc(tz, d, minutes)
    return start, start + dt.timedelta(minutes=dur), dur


def book(conn, user, f, confirm=False, now=None):
    now = now or utcnow()
    tz = tz_of(conn)
    errors = {}
    note = (f.get("note") or "").strip()
    if len(note) > NOTE_MAX:
        errors["note"] = "The note can be at most %d characters." % NOTE_MAX
    for k in ("practitioner_id", "patient_id", "type_id"):
        try:
            int(f.get(k) or "")
        except ValueError:
            errors[k] = "Choose a %s." % k.split("_")[0].replace("type", "appointment type")
    if errors:
        raise ValidationError(errors)
    start, end, dur = _parse_when(conn, tz, f)
    with tx(conn):
        pr = conn.execute("SELECT * FROM practitioners WHERE id=?", (int(f["practitioner_id"]),)).fetchone()
        if not pr or pr["archived"]:
            raise ValidationError({"practitioner_id": "Choose an active practitioner."})
        ty = conn.execute("SELECT * FROM appt_types WHERE id=?", (int(f["type_id"]),)).fetchone()
        if not ty or ty["archived"]:
            raise ValidationError({"type_id": "Choose an active appointment type."})
        pat = conn.execute("SELECT * FROM patients WHERE id=?", (int(f["patient_id"]),)).fetchone()
        if not pat or pat["archived"]:
            raise ValidationError({"patient_id": "Patient not found (it may have been archived)."})
        check_slot(conn, tz, pr["id"], pat["id"], start, end, None, now, confirm)
        aid = conn.execute("""INSERT INTO appointments(practitioner_id,patient_id,type_id,start_utc,end_utc,duration,note,status,
                              created_by,created_at,updated_by,updated_at) VALUES(?,?,?,?,?,?,?,'booked',?,?,?,?)""",
                           (pr["id"], pat["id"], ty["id"], to_s(start), to_s(end), dur, note, user["id"], to_s(now), user["id"],
                            to_s(now))).lastrowid
        history(conn, aid, "created", user["id"], now, {"start": fmt_dt(tz, to_s(start)), "duration": dur,
                                                        "practitioner": pr["name"], "type": ty["name"]})
        schedule_reminder(conn, aid, now, user["id"])
    return aid


def move(conn, user, aid, f, confirm=False, now=None):
    now = now or utcnow()
    tz = tz_of(conn)
    start, end, dur = _parse_when(conn, tz, f)
    with tx(conn):
        a = get_appt(conn, aid)
        if a["status"] != "booked":
            raise ValidationError("Only booked appointments can be moved.")
        if str(a["version"]) != str(f.get("version")):
            raise Stale("This appointment was changed by %s; reload." % username_of(conn, a["updated_by"]))
        pid = int(f.get("practitioner_id") or a["practitioner_id"])
        pr = conn.execute("SELECT * FROM practitioners WHERE id=?", (pid,)).fetchone()
        if not pr or (pr["archived"] and pid != a["practitioner_id"]):
            raise ValidationError({"practitioner_id": "Choose an active practitioner."})
        if (to_s(start), to_s(end), pid) == (a["start_utc"], a["end_utc"], a["practitioner_id"]):
            raise ValidationError("Nothing to change: pick a new date, time, practitioner or duration.")
        check_slot(conn, tz, pid, a["patient_id"], start, end, aid, now, confirm)
        _bump(conn, "appointments", aid, a["version"], "practitioner_id=?, start_utc=?, end_utc=?, duration=?, updated_by=?, updated_at=?",
              (pid, to_s(start), to_s(end), dur, user["id"], to_s(now)))
        history(conn, aid, "moved", user["id"], now, {
            "old": "%s, %d min, %s" % (fmt_dt(tz, a["start_utc"]), a["duration"], a["pr_name"]),
            "new": "%s, %d min, %s" % (fmt_dt(tz, to_s(start)), dur, pr["name"])})
        if to_s(start) != a["start_utc"]:
            schedule_reminder(conn, aid, now, user["id"])


def cancel(conn, user, aid, reason, text, version, now=None):
    now = now or utcnow()
    tz = tz_of(conn)
    if reason not in CANCEL_REASONS:
        raise ValidationError({"reason": "Choose a reason."})
    text = (text or "").strip()
    if reason == "other" and not text:
        raise ValidationError({"text": "Describe the reason in a few words."})
    if len(text) > 100:
        raise ValidationError({"text": "Keep the reason under 100 characters."})
    with tx(conn):
        a = get_appt(conn, aid)
        _check_version(conn, a, version)
        if a["status"] != "booked":
            raise ValidationError("Only booked appointments can be cancelled.")
        late = 1 if from_s(a["start_utc"]) - now < dt.timedelta(hours=LATE_CANCEL_HOURS) else 0
        _bump(conn, "appointments", aid, version, "status='cancelled', cancel_reason=?, cancel_text=?, late_cancel=?, updated_by=?, updated_at=?",
              (reason, text, late, user["id"], to_s(now)))
        history(conn, aid, "cancelled", user["id"], now, {"reason": CANCEL_REASONS[reason] + (": " + text if text else ""),
                                                          "late": bool(late)})
        conn.execute("""UPDATE reminders SET state='not_needed', reason='cancelled', next_attempt_utc=NULL
                        WHERE appointment_id=? AND kind IN ('reminder','changed') AND state IN ('pending','failed')""", (aid,))
        if (get_setting(conn, "reminders.cancellation_email") == "on" and a["email"]
                and from_s(a["start_utc"]) > now):
            _insert_reminder(conn, aid, "cancellation", a["start_utc"], now, "pending", "", user["id"], now)
    return late


def set_status(conn, user, aid, status, version, now=None):
    now = now or utcnow()
    if status not in ("attended", "no_show"):
        raise ValidationError("Unknown status.")
    with tx(conn):
        a = get_appt(conn, aid)
        _check_version(conn, a, version)
        if a["status"] != "booked":
            raise ValidationError("Only booked appointments can be marked %s." % STATUS_LABEL[status])
        if now < from_s(a["start_utc"]):
            raise ValidationError("%s can only be set from the start time onward." % STATUS_LABEL[status])
        _bump(conn, "appointments", aid, version, "status=?, updated_by=?, updated_at=?", (status, user["id"], to_s(now)))
        history(conn, aid, "status", user["id"], now, {"old": "Booked", "new": STATUS_LABEL[status]})
        conn.execute("""UPDATE reminders SET state='not_needed', reason=?, next_attempt_utc=NULL
                        WHERE appointment_id=? AND kind IN ('reminder','changed') AND state='pending'""",
                     ("appointment " + STATUS_LABEL[status].lower(), aid))


def _check_version(conn, a, version):
    if str(a["version"]) != str(version):
        raise Stale("This appointment was changed by %s; reload." % username_of(conn, a["updated_by"]))


def undo_deadline(tz, a):
    d = local(tz, a["start_utc"]).date() + dt.timedelta(days=2)
    return dt.datetime.combine(d, dt.time(0)).replace(tzinfo=tz).astimezone(UTC)


def undo(conn, user, aid, version, now=None):
    now = now or utcnow()
    tz = tz_of(conn)
    with tx(conn):
        a = get_appt(conn, aid)
        _check_version(conn, a, version)
        if a["status"] == "booked":
            raise ValidationError("This appointment is already booked.")
        if now >= undo_deadline(tz, a):
            raise ValidationError("Too late to undo: changes can be undone until the end of the day after the appointment.")
        if a["status"] == "cancelled":
            msg = overlap_conflict(conn, tz, a["practitioner_id"], a["start_utc"], a["end_utc"], aid)
            if msg:
                raise Conflict(msg + ". The appointment stays cancelled; you can move it instead.")
            if get_setting(conn, "booking.patient_overlap") == "block":
                po = patient_overlap(conn, tz, a["patient_id"], a["start_utc"], a["end_utc"], aid)
                if po:
                    raise Conflict(po + ". The appointment stays cancelled.")
        _bump(conn, "appointments", aid, version, "status='booked', cancel_reason=NULL, cancel_text=NULL, late_cancel=0, updated_by=?, updated_at=?",
              (user["id"], to_s(now)))
        history(conn, aid, "undo", user["id"], now, {"old": STATUS_LABEL[a["status"]], "new": "Booked"})
        if from_s(a["start_utc"]) > now:
            conn.execute("UPDATE reminders SET state='superseded', next_attempt_utc=NULL WHERE appointment_id=? AND kind='cancellation' "
                         "AND state='pending'", (aid,))
            schedule_reminder(conn, aid, now, user["id"])


# ---------------------------------------------------------------- reminders
REM_LABEL = {"pending": "Pending", "sending": "Sending", "sent": "Sent", "failed": "Failed", "skipped": "Skipped",
             "not_needed": "Not needed", "superseded": "Superseded"}


def _insert_reminder(conn, aid, kind, start_s, due, state, reason, user_id, now, manual=0):
    return conn.execute("""INSERT INTO reminders(appointment_id,kind,appt_start_utc,due_utc,next_attempt_utc,state,reason,manual,created_at,created_by)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (aid, kind, start_s, to_s(due), to_s(due) if state == "pending" else None, state, reason, manual,
                         to_s(now), user_id)).lastrowid


def current_reminder(conn, aid):
    return conn.execute("""SELECT * FROM reminders WHERE appointment_id=? AND kind IN ('reminder','changed') AND state!='superseded'
                           ORDER BY id DESC LIMIT 1""", (aid,)).fetchone()


def schedule_reminder(conn, aid, now, user_id, force_new=False):
    """(Re)plan the single reminder for the appointment's current time. Call inside a transaction."""
    a = conn.execute("SELECT a.*, p.email, p.send_reminders FROM appointments a JOIN patients p ON p.id=a.patient_id WHERE a.id=?",
                     (aid,)).fetchone()
    rows = conn.execute("SELECT * FROM reminders WHERE appointment_id=? AND kind IN ('reminder','changed')", (aid,)).fetchall()
    if any(r["state"] in ("sent", "sending") and r["appt_start_utc"] == a["start_utc"] for r in rows) and not force_new:
        return  # already sent for this exact time: at most once per appointment time
    any_sent = any(r["state"] == "sent" and r["appt_start_utc"] != a["start_utc"] for r in rows)
    conn.execute("""UPDATE reminders SET state='superseded', next_attempt_utc=NULL WHERE appointment_id=? AND kind IN ('reminder','changed')
                    AND state IN ('pending','failed','skipped','not_needed')""", (aid,))
    kind = "changed" if any_sent else "reminder"
    start = from_s(a["start_utc"])
    due = start - dt.timedelta(hours=REMINDER_LEAD_HOURS)
    state, reason = "pending", ""
    if not a["email"]:
        state, reason = "skipped", "no email"
    elif not a["send_reminders"]:
        state, reason = "skipped", "opted out"
    elif now >= due:
        if start - now > dt.timedelta(hours=IMMEDIATE_MIN_HOURS):
            due = now
        else:
            state, reason = "skipped", "too late"
    if a["status"] != "booked":
        state, reason = "not_needed", STATUS_LABEL[a["status"]].lower()
    _insert_reminder(conn, aid, kind, a["start_utc"], due, state, reason, user_id, now)


def reminder_text(tz, r):
    """Short label used on the day view, appointment page and confirmation."""
    if r is None:
        return "No reminder"
    if r["state"] == "pending":
        return "Reminder due %s" % fmt_dt(tz, r["next_attempt_utc"] or r["due_utc"]) + (" (retry %d)" % r["attempts"] if r["attempts"] else "")
    if r["state"] == "sent":
        return "Reminder sent %s" % fmt_dt(tz, r["sent_at"])
    if r["state"] == "skipped":
        return "No reminder: %s" % r["reason"]
    if r["state"] == "failed":
        return "Reminder failed: %s" % r["reason"]
    if r["state"] == "not_needed":
        return "Reminder not needed"
    return REM_LABEL.get(r["state"], r["state"])


def retry_reminder(conn, user, rid, now=None):
    now = now or utcnow()
    with tx(conn):
        r = conn.execute("SELECT * FROM reminders WHERE id=?", (rid,)).fetchone()
        if not r or r["state"] != "failed":
            raise ValidationError("Only failed reminders can be retried.")
        a = get_appt(conn, r["appointment_id"])
        if r["kind"] != "cancellation" and (a["status"] != "booked" or from_s(a["start_utc"]) <= now or a["start_utc"] != r["appt_start_utc"]):
            raise ValidationError("The appointment is no longer upcoming at that time; nothing to retry.")
        conn.execute("UPDATE reminders SET state='pending', attempts=0, reason='', manual=1, next_attempt_utc=? WHERE id=?", (to_s(now), rid))
        audit(conn, user["id"], "reminder", "retry reminder %d" % rid, now)


def resend_reminder(conn, user, aid, now=None):
    now = now or utcnow()
    with tx(conn):
        a = get_appt(conn, aid)
        if a["status"] != "booked" or from_s(a["start_utc"]) <= now:
            raise ValidationError("Reminders can only be sent for upcoming booked appointments.")
        if not a["email"]:
            raise ValidationError("The patient has no email address.")
        cur = current_reminder(conn, aid)
        kind = cur["kind"] if cur else "reminder"
        conn.execute("""UPDATE reminders SET state='superseded', next_attempt_utc=NULL WHERE appointment_id=? AND kind IN ('reminder','changed')
                        AND state IN ('pending','failed','skipped')""", (aid,))
        _insert_reminder(conn, aid, kind, a["start_utc"], now, "pending", "", user["id"], now, manual=1)
        history(conn, aid, "resend", user["id"], now, {"to": a["email"]})


def recover_interrupted(conn, now=None):
    """At start: a send that was in progress when the service stopped is never repeated automatically."""
    with tx(conn):
        conn.execute("""UPDATE reminders SET state='failed', next_attempt_utc=NULL,
                        reason='interrupted while sending; it may or may not have arrived (use Resend if needed)' WHERE state='sending'""")


def render_email(conn, r):
    tz = tz_of(conn)
    c = conn.execute("SELECT * FROM clinic WHERE id=1").fetchone()
    a = get_appt(conn, r["appointment_id"])
    l = local(tz, r["appt_start_utc"])
    when = "%s %d %s %d at %s" % (l.strftime("%A"), l.day, l.strftime("%B"), l.year, l.strftime("%H:%M"))
    pr = conn.execute("SELECT name, title FROM practitioners WHERE id=?", (a["practitioner_id"],)).fetchone()
    who = (pr["title"] + " " + pr["name"]).strip()
    contact = "\n".join(x for x in (c["name"], c["address"], ("Phone: " + c["phone"]) if c["phone"] else "") if x)
    if r["kind"] == "cancellation":
        subject = "Your appointment has been cancelled"
        body = ("Dear %s,\n\nYour appointment on %s with %s at %s has been cancelled.\n\n"
                "To book a new appointment, call %s.\n\n%s\n") % (a["first_name"], when, who, c["name"], c["phone"] or "the clinic", contact)
    else:
        subject = "Your appointment has changed" if r["kind"] == "changed" else "Appointment reminder: %s" % when
        intro = "Your appointment has changed. The new time is:" if r["kind"] == "changed" else "This is a reminder of your appointment:"
        body = ("Dear %s,\n\n%s\n\n  Date and time: %s\n  With: %s\n  At: %s\n\n"
                "To change or cancel, call %s.\n\n%s\n") % (a["first_name"], intro, when, who, c["name"], c["phone"] or "the clinic", contact)
    return a["email"], subject, body, c["reply_to"]


def process_due(conn, send, now=None, user_id=None):
    """Send every pending email that is due. `send(to, subject, body, reply_to)` raises on failure. Returns count attempted."""
    now = now or utcnow()
    due = conn.execute("SELECT id FROM reminders WHERE state='pending' AND next_attempt_utc<=? ORDER BY next_attempt_utc, id",
                       (to_s(now),)).fetchall()
    n = 0
    for (rid,) in due:
        with tx(conn):
            r = conn.execute("SELECT * FROM reminders WHERE id=? AND state='pending'", (rid,)).fetchone()
            if not r:
                continue
            a = get_appt(conn, r["appointment_id"])
            if r["kind"] != "cancellation":
                if a["status"] != "booked" or a["start_utc"] != r["appt_start_utc"]:
                    conn.execute("UPDATE reminders SET state='superseded', next_attempt_utc=NULL WHERE id=?", (rid,))
                    continue
                if not r["manual"] and from_s(a["start_utc"]) - now <= dt.timedelta(hours=CATCHUP_MIN_HOURS):
                    conn.execute("UPDATE reminders SET state='skipped', reason='too late', next_attempt_utc=NULL WHERE id=?", (rid,))
                    continue
            if not a["email"]:
                conn.execute("UPDATE reminders SET state='skipped', reason='no email', next_attempt_utc=NULL WHERE id=?", (rid,))
                continue
            # record the attempt before sending, so a crash can never lead to a silent duplicate
            conn.execute("UPDATE reminders SET state='sending', attempts=attempts+1 WHERE id=?", (rid,))
            to, subject, body, reply_to = render_email(conn, r)
        n += 1
        try:
            send(to, subject, body, reply_to)
            err = None
        except Exception as e:  # noqa: BLE001 - any mail failure is reported, not raised
            err = (str(e) or e.__class__.__name__)[:300]
        with tx(conn):
            r = conn.execute("SELECT * FROM reminders WHERE id=?", (rid,)).fetchone()
            if err is None:
                conn.execute("UPDATE reminders SET state='sent', sent_at=?, reason='', next_attempt_utc=NULL WHERE id=?", (to_s(now), rid))
            elif r["attempts"] <= RETRIES:
                conn.execute("UPDATE reminders SET state='pending', reason=?, next_attempt_utc=? WHERE id=?",
                             (err, to_s(now + dt.timedelta(minutes=RETRY_MINUTES)), rid))
            else:
                conn.execute("UPDATE reminders SET state='failed', reason=?, next_attempt_utc=NULL WHERE id=?", (err, rid))
            conn.execute("INSERT INTO email_log(at,reminder_id,appointment_id,recipient,kind,result,error,user_id) VALUES(?,?,?,?,?,?,?,?)",
                         (to_s(now), rid, r["appointment_id"], to, r["kind"] + (" (manual)" if r["manual"] else ""),
                          "sent" if err is None else "failed", err or "", r["created_by"] if r["manual"] else None))
    return n


def last_sends_failed(conn, n=3):
    rows = conn.execute("SELECT result FROM email_log WHERE kind!='test' ORDER BY id DESC LIMIT ?", (n,)).fetchall()
    return len(rows) == n and all(r["result"] == "failed" for r in rows)


# ---------------------------------------------------------------- reports
def parse_range(f):
    d1 = parse_date(f.get("from"), "from")
    d2 = parse_date(f.get("to"), "to")
    if d2 < d1:
        raise ValidationError({"to": "The end date is before the start date."})
    if (d2 - d1).days + 1 > EXPORT_MAX_DAYS:
        raise ValidationError({"to": "The range can be at most %d days." % EXPORT_MAX_DAYS})
    return d1, d2


def appts_in_range(conn, d1, d2, pids=None):
    tz = tz_of(conn)
    s, _ = day_bounds(tz, d1)
    _, e = day_bounds(tz, d2)
    q = APPT_SELECT + " WHERE a.start_utc>=? AND a.start_utc<?"
    params = [to_s(s), to_s(e)]
    if pids:
        q += " AND a.practitioner_id IN (%s)" % ",".join("?" * len(pids))
        params += list(pids)
    rows = conn.execute(q + " ORDER BY a.start_utc, pr.name", params).fetchall()
    return [(a, current_reminder(conn, a["id"])) for a in rows]


def summary(conn, d1, d2):
    out = {}
    for a, r in appts_in_range(conn, d1, d2):
        s = out.setdefault(a["pr_name"], {"booked": 0, "attended": 0, "no_show": 0, "cancelled": 0, "late_cancelled": 0,
                                         "reminders_sent": 0, "reminders_failed": 0, "total": 0})
        s[a["status"]] += 1
        s["total"] += 1
        s["late_cancelled"] += 1 if a["status"] == "cancelled" and a["late_cancel"] else 0
        s["reminders_sent"] += 1 if r is not None and r["state"] == "sent" else 0
        s["reminders_failed"] += 1 if r is not None and r["state"] == "failed" else 0
    return dict(sorted(out.items()))


def _csv_safe(v):
    v = "" if v is None else str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") and not re.fullmatch(r"\+?[\d \-]+", v) else v


CSV_HEADER = ["date", "start", "end", "practitioner", "patient", "phone", "email", "type", "status", "cancel reason",
              "late cancellation", "reminder state", "created by"]


def export_rows(conn, d1, d2):
    tz = tz_of(conn)
    users = {r["id"]: r["username"] for r in conn.execute("SELECT id, username FROM users")}
    for a, r in appts_in_range(conn, d1, d2):
        ls, le = local(tz, a["start_utc"]), local(tz, a["end_utc"])
        reason = ""
        if a["status"] == "cancelled":
            reason = CANCEL_REASONS.get(a["cancel_reason"], "") + (": " + a["cancel_text"] if a["cancel_text"] else "")
        rem = "None" if r is None else REM_LABEL[r["state"]] + (" (%s)" % r["reason"] if r["state"] == "skipped" else "")
        yield [_csv_safe(x) for x in (ls.date().isoformat(), ls.strftime("%H:%M"), le.strftime("%H:%M"), a["pr_name"],
                                      a["first_name"] + " " + a["last_name"], a["phone"], a["email"], a["type_name"],
                                      STATUS_LABEL[a["status"]], reason, "yes" if a["late_cancel"] else "no", rem,
                                      users.get(a["created_by"], ""))]
