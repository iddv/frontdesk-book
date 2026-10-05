"""SQLite storage, versioned migrations, backup and restore."""
import datetime as _dt
import os
import shutil
import sqlite3
from contextlib import contextmanager

DB_NAME = "frontdesk.db"

MIGRATIONS = [
    # 1: initial schema
    """
    CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE clinic(
        id INTEGER PRIMARY KEY CHECK (id = 1),
        name TEXT NOT NULL, tz TEXT NOT NULL,
        address TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '', reply_to TEXT NOT NULL DEFAULT '',
        email_mode TEXT NOT NULL DEFAULT 'log', smtp_host TEXT NOT NULL DEFAULT '', smtp_port INTEGER NOT NULL DEFAULT 587,
        smtp_tls TEXT NOT NULL DEFAULT 'starttls', smtp_user TEXT NOT NULL DEFAULT '', smtp_password TEXT NOT NULL DEFAULT '',
        smtp_from TEXT NOT NULL DEFAULT '', demo INTEGER NOT NULL DEFAULT 0,
        version INTEGER NOT NULL DEFAULT 1, updated_by INTEGER, updated_at TEXT);
    CREATE TABLE users(
        id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE, role TEXT NOT NULL CHECK (role IN ('admin','receptionist')),
        pw_hash TEXT NOT NULL, must_change INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
        failed_count INTEGER NOT NULL DEFAULT 0, locked_until TEXT, created_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE sessions(token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
        last_seen TEXT NOT NULL, flash TEXT);
    CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE audit_log(id INTEGER PRIMARY KEY, at TEXT NOT NULL, user_id INTEGER, kind TEXT NOT NULL, detail TEXT NOT NULL);
    CREATE TABLE practitioners(id INTEGER PRIMARY KEY, name TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', colour TEXT NOT NULL DEFAULT '#4a90d9',
        archived INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
    CREATE TABLE practitioner_hours(id INTEGER PRIMARY KEY, practitioner_id INTEGER NOT NULL REFERENCES practitioners(id),
        weekday INTEGER NOT NULL, start_min INTEGER NOT NULL, end_min INTEGER NOT NULL);
    CREATE TABLE timeoff(id INTEGER PRIMARY KEY, practitioner_id INTEGER NOT NULL REFERENCES practitioners(id),
        start_date TEXT NOT NULL, end_date TEXT NOT NULL, start_min INTEGER, end_min INTEGER, label TEXT NOT NULL,
        created_by INTEGER, created_at TEXT NOT NULL);
    CREATE TABLE appt_types(id INTEGER PRIMARY KEY, name TEXT NOT NULL, duration INTEGER NOT NULL,
        archived INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE patients(id INTEGER PRIMARY KEY, first_name TEXT NOT NULL, last_name TEXT NOT NULL, dob TEXT,
        phone TEXT NOT NULL DEFAULT '', phone_digits TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '',
        send_reminders INTEGER NOT NULL DEFAULT 1, archived INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL, updated_at TEXT, updated_by INTEGER);
    CREATE TABLE appointments(id INTEGER PRIMARY KEY,
        practitioner_id INTEGER NOT NULL REFERENCES practitioners(id), patient_id INTEGER NOT NULL REFERENCES patients(id),
        type_id INTEGER NOT NULL REFERENCES appt_types(id), start_utc TEXT NOT NULL, end_utc TEXT NOT NULL,
        duration INTEGER NOT NULL, note TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'booked' CHECK (status IN ('booked','attended','no_show','cancelled')),
        cancel_reason TEXT, cancel_text TEXT, late_cancel INTEGER NOT NULL DEFAULT 0,
        created_by INTEGER, created_at TEXT NOT NULL, updated_by INTEGER, updated_at TEXT,
        version INTEGER NOT NULL DEFAULT 1);
    CREATE INDEX appt_pr_start ON appointments(practitioner_id, start_utc);
    CREATE INDEX appt_pat_start ON appointments(patient_id, start_utc);
    CREATE INDEX appt_start ON appointments(start_utc);
    CREATE TABLE appt_history(id INTEGER PRIMARY KEY, appointment_id INTEGER NOT NULL REFERENCES appointments(id),
        at TEXT NOT NULL, user_id INTEGER, action TEXT NOT NULL, details TEXT NOT NULL DEFAULT '');
    CREATE INDEX hist_appt ON appt_history(appointment_id);
    CREATE TABLE reminders(id INTEGER PRIMARY KEY, appointment_id INTEGER NOT NULL REFERENCES appointments(id),
        kind TEXT NOT NULL, appt_start_utc TEXT NOT NULL, due_utc TEXT NOT NULL, next_attempt_utc TEXT,
        state TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '', attempts INTEGER NOT NULL DEFAULT 0, manual INTEGER NOT NULL DEFAULT 0,
        sent_at TEXT, created_at TEXT NOT NULL, created_by INTEGER);
    CREATE INDEX rem_state ON reminders(state, next_attempt_utc);
    CREATE INDEX rem_appt ON reminders(appointment_id);
    CREATE TABLE email_log(id INTEGER PRIMARY KEY, at TEXT NOT NULL, reminder_id INTEGER, appointment_id INTEGER,
        recipient TEXT NOT NULL, kind TEXT NOT NULL, result TEXT NOT NULL, error TEXT NOT NULL DEFAULT '', user_id INTEGER);
    """,
]

LATEST = len(MIGRATIONS)
REQUIRED_TABLES = {"clinic", "users", "patients", "appointments", "reminders", "meta"}


def db_path(data_dir):
    return os.path.join(data_dir, DB_NAME)


def connect(path):
    conn = sqlite3.connect(path, timeout=30, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


@contextmanager
def tx(conn):
    """A write transaction that takes the database write lock up front, so check-then-save is atomic."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def schema_version(conn):
    has = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone()
    if not has:
        return 0
    row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    return int(row[0]) if row else 0


def stamp():
    return _dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def migrate(data_dir, log=print):
    """Apply pending migrations; takes an automatic backup first when upgrading existing data."""
    path = db_path(data_dir)
    existed = os.path.exists(path)
    conn = connect(path)
    try:
        current = schema_version(conn)
        if current > LATEST:
            raise SystemExit("The data was created by a newer version of FrontDesk Book (schema %d > %d)." % (current, LATEST))
        if current < LATEST and existed and current > 0:
            dest = os.path.join(data_dir, "backups", "pre-upgrade-v%d-%s.db" % (current, stamp()))
            backup_to(conn, dest)
            log("Backed up data to %s before upgrading" % dest)
        for v in range(current + 1, LATEST + 1):
            conn.executescript("BEGIN IMMEDIATE;" + MIGRATIONS[v - 1] +
                               ";INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version','%d');COMMIT;" % v)
            log("Applied schema migration %d" % v)
    finally:
        conn.close()


def backup_to(conn, dest):
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    out = sqlite3.connect(dest)
    try:
        conn.backup(out)
    finally:
        out.close()
    return dest


def validate_backup(path):
    try:
        c = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
        names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        ok = c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        c.close()
    except sqlite3.DatabaseError as e:
        raise SystemExit("Not a FrontDesk Book backup file: %s" % e)
    if not ok or not REQUIRED_TABLES <= names:
        raise SystemExit("Not a valid FrontDesk Book backup file.")


def restore(data_dir, backup_file, log=print):
    validate_backup(backup_file)
    path = db_path(data_dir)
    os.makedirs(data_dir, exist_ok=True)
    if os.path.exists(path):
        kept = os.path.join(data_dir, "replaced-%s.db" % stamp())
        conn = connect(path)
        backup_to(conn, kept)
        conn.close()
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(path + suffix):
                os.remove(path + suffix)
        log("Previous data kept as %s" % kept)
    shutil.copyfile(backup_file, path)
    log("Restored %s" % backup_file)
