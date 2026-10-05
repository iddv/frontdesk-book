"""HTTP layer: routing, sessions, permissions and server-rendered pages."""
import csv
import datetime as dt
import hmac
import html
import io
import json
import logging
import os
import re
import secrets
import sqlite3
import tempfile
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler

from . import db, domain as D, mailer
from .domain import ValidationError, Conflict, Stale, NotFound, NeedsConfirm, AppError

log = logging.getLogger("frontdesk.web")
PX = 1.3  # pixels per minute on the day view


def e(v):
    return html.escape("" if v is None else str(v), quote=True)


class HTTPError(Exception):
    def __init__(self, code, msg):
        self.code, self.msg = code, msg


class Redirect(Exception):
    def __init__(self, url, flash=None):
        self.url, self.flash = url, flash


class Req:
    def __init__(self, app, method, path, query, form, cookies, headers):
        self.app, self.method, self.path, self.query, self.form = app, method, path, query, form
        self.cookies, self.headers = cookies, headers
        self.conn = None
        self.user = None
        self.token = None
        self.now = D.utcnow()
        self.flash = None
        self.set_cookie = None

    def q(self, k, default=""):
        return (self.query.get(k) or [default])[0]

    def f(self, k, default=""):
        return (self.form.get(k) or [default])[0]

    def fdict(self):
        return {k: v[0] for k, v in self.form.items()}

    @property
    def csrf(self):
        return hmac.new(self.app.secret, (self.token or "").encode(), "sha256").hexdigest()[:32]

    @property
    def tz(self):
        return D.tz_of(self.conn)

    @property
    def today(self):
        return D.local(self.tz, self.now).date()

    @property
    def is_admin(self):
        return self.user is not None and self.user["role"] == "admin"


ROUTES = []


def route(method, pattern, role="staff"):
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), role, fn))
        return fn
    return deco


# ------------------------------------------------------------------ rendering helpers
CSS = """
*{box-sizing:border-box}body{font:14px/1.4 system-ui,Segoe UI,Arial,sans-serif;margin:0;color:#222;background:#f6f7f9}
a{color:#1a5fb4}header{background:#24405f;color:#fff;padding:6px 12px;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
header a{color:#fff;text-decoration:none}header a:hover{text-decoration:underline}header .who{margin-left:auto}
header form{display:inline}header button{background:none;border:0;color:#fff;cursor:pointer;font:inherit;text-decoration:underline}
main{padding:12px 16px}h1{font-size:20px;margin:4px 0 12px}h2{font-size:16px;margin:18px 0 8px}
.banner{background:#fff3cd;border-bottom:1px solid #e0c36b;padding:6px 12px}.banner.bad{background:#f8d7da;border-color:#d99}
.flash{background:#d1e7dd;border:1px solid #9bc9b0;padding:8px;margin-bottom:10px;border-radius:4px}
.err{color:#b00020;font-size:13px}.errbox{background:#f8d7da;border:1px solid #d99;padding:8px;margin-bottom:10px;border-radius:4px}
.warnbox{background:#fff3cd;border:1px solid #e0c36b;padding:8px;margin-bottom:10px;border-radius:4px}
table{border-collapse:collapse;background:#fff}td,th{border:1px solid #ccd;padding:4px 8px;text-align:left;vertical-align:top}
th{background:#eef1f5}label{display:block;margin:6px 0 2px;font-weight:600}input,select,textarea{font:inherit;padding:4px}
input[type=text],input[type=email],input[type=password],input[type=tel],textarea{width:min(100%,360px)}
button,.btn{font:inherit;padding:4px 10px;border:1px solid #889;border-radius:4px;background:#fff;cursor:pointer;color:#222;text-decoration:none;display:inline-block}
button.primary{background:#1a5fb4;color:#fff;border-color:#1a5fb4}button.danger{color:#b00020;border-color:#b00020}
form.inline{display:inline}.card{background:#fff;border:1px solid #ccd;border-radius:6px;padding:10px 14px;margin-bottom:12px;max-width:900px}
.muted{color:#666}.row{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start}
.grid{display:flex;gap:6px;align-items:flex-start;overflow-x:auto}.axis{position:relative;width:44px;flex:none}
.axis div{position:absolute;right:4px;font-size:11px;color:#666;transform:translateY(-6px)}
.col{flex:1 0 170px;max-width:340px}.colhead{font-weight:700;padding:4px;border-bottom:3px solid #888;background:#fff;white-space:nowrap;overflow:hidden}
.colbody{position:relative;background:#e3e4e8;border:1px solid #ccd}.hrs{position:absolute;left:0;right:0;background:#fff}
.off{position:absolute;left:0;right:0;background:repeating-linear-gradient(45deg,#ddd,#ddd 6px,#c8c8c8 6px,#c8c8c8 12px);font-size:11px;padding:2px;color:#444}
.hl{position:absolute;left:0;right:0;border-top:1px solid #d0d3da}.slot{position:absolute;left:0;right:0;display:block}
.slot:hover{background:rgba(26,95,180,.15)}.ap{position:absolute;left:3px;right:3px;border-radius:4px;padding:2px 4px;font-size:12px;overflow:hidden;
border-left:5px solid;background:#eaf2fc;color:#111;text-decoration:none;box-shadow:0 1px 2px rgba(0,0,0,.25)}
.ap.attended{background:#ddf3e4}.ap.no_show{background:#f8dddd}.ap .flag{color:#b00020;font-weight:700}.ap form{display:inline}
.ap button{font-size:11px;padding:0 4px}.cx{font-size:12px;color:#666;padding:4px}.nowline{position:absolute;left:0;right:0;border-top:2px solid #d00}
.st-booked{color:#1a5fb4}.st-attended{color:#1b7f3b}.st-no_show{color:#b00020}.st-cancelled{color:#666;text-decoration:line-through}
.checklist li.done{color:#1b7f3b}
@media print{header,.banner,.noprint{display:none!important}main{padding:0}body{background:#fff}.sheet{page-break-after:always}
.sheet:last-child{page-break-after:auto}table{width:100%}@page{margin:12mm}}
"""


def field_err(errors, k):
    return '<div class="err">%s</div>' % e(errors[k]) if errors and k in errors else ""


def errbox(errors, keys=()):
    if not errors:
        return ""
    other = [v for k, v in errors.items() if k not in keys]
    return '<div class="errbox">%s</div>' % "<br>".join(e(m) for m in other) if other else ""


def hidden(req):
    return '<input type="hidden" name="_csrf" value="%s">' % e(req.csrf)


def post_button(req, action, label, fields=None, cls="", confirm=None):
    extra = "".join('<input type="hidden" name="%s" value="%s">' % (e(k), e(v)) for k, v in (fields or {}).items())
    onsub = ' onsubmit="return confirm(%s)"' % e(json.dumps(confirm)) if confirm else ""
    return '<form class="inline" method="post" action="%s"%s>%s%s<button class="%s">%s</button></form>' % (
        e(action), onsub, hidden(req), extra, cls, e(label))


def inp(name, value="", errors=None, label=None, type="text", **attrs):
    a = "".join(' %s="%s"' % (k.rstrip("_").replace("_", "-"), e(v)) for k, v in attrs.items() if v is not None and v is not False)
    lab = '<label for="%s">%s</label>' % (name, e(label)) if label else ""
    return '%s<input type="%s" id="%s" name="%s" value="%s"%s>%s' % (lab, type, name, name, e(value), a, field_err(errors, name))


def select(name, options, value, errors=None, label=None, attrs=""):
    lab = '<label for="%s">%s</label>' % (name, e(label)) if label else ""
    opts = "".join('<option value="%s"%s>%s</option>' % (e(v), " selected" if str(v) == str(value) else "", e(t)) for v, t in options)
    return '%s<select id="%s" name="%s"%s>%s</select>%s' % (lab, name, name, attrs, opts, field_err(errors, name))


def page(req, title, body, status=200):
    nav = ""
    banner = ""
    if req.user:
        links = [("/day", "Day"), ("/week", "Week"), ("/patients", "Patients"), ("/appt/new", "New appointment"),
                 ("/reminders", "Reminders"), ("/daysheet", "Day sheet"), ("/summary", "Summary"), ("/export", "Export")]
        if req.is_admin:
            links.append(("/admin", "Setup"))
        nav = "".join('<a href="%s">%s</a>' % (u, t) for u, t in links)
        nav = ('<header><strong>%s</strong>%s<span class="who">%s (%s) &middot; <a href="/password">Change password</a> &middot; '
               '<form method="post" action="/logout">%s<button>Sign out</button></form></span></header>') % (
            e(req.conn.execute("SELECT name FROM clinic").fetchone()["name"]), nav, e(req.user["username"]), e(req.user["role"]), hidden(req))
        s = mailer.effective(req.conn, req.app.cfg)
        if not mailer.is_configured(s):
            banner += ('<div class="banner">Email is not configured: reminder emails are written to the outbox file in the data '
                       'directory, not sent to patients.%s</div>') % (' <a href="/admin/email">Configure email</a>' if req.is_admin else "")
        if D.last_sends_failed(req.conn):
            banner += '<div class="banner bad">The last 3 emails failed to send. <a href="/reminders">See Reminders</a>.</div>'
    flash = '<div class="flash">%s</div>' % e(req.flash) if req.flash else ""
    doc = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
           '<title>%s – FrontDesk Book</title><style>%s</style></head><body>%s%s<main>%s<h1>%s</h1>%s</main></body></html>') % (
        e(title), CSS, nav, banner, flash, e(title), body)
    return status, {"Content-Type": "text/html; charset=utf-8"}, doc.encode()


def url(path, **params):
    items = []
    for k, v in params.items():
        if isinstance(v, (list, tuple)):
            items += [(k, x) for x in v]
        elif v not in (None, ""):
            items.append((k, v))
    return path + ("?" + urllib.parse.urlencode(items) if items else "")


def parse_day(req, key="date"):
    try:
        return D.parse_date(req.q(key)) if req.q(key) else req.today
    except ValidationError:
        return req.today


# ------------------------------------------------------------------ auth pages
@route("GET", "/setup", role="public")
def setup_get(req, errors=None, f=None):
    if req.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        raise Redirect("/login")
    f = f or {"tz": D.machine_tz()}
    tzs = "".join('<option value="%s">' % e(z) for z in sorted(D.ZoneInfo.__module__ and __import__("zoneinfo").available_timezones()))
    body = """<div class="card"><p>Welcome. No accounts exist yet: set up the clinic and the first admin account.</p>
    %s<form method="post">%s%s<datalist id="tzs">%s</datalist>%s%s
    <p class="muted">Password: at least %d characters.</p>%s%s<p><button class="primary">Create clinic and admin</button></p></form></div>""" % (
        errbox(errors, ("clinic_name", "tz", "username", "password", "password2")), hidden(req),
        inp("clinic_name", f.get("clinic_name"), errors, "Clinic name", required=True),
        tzs, inp("tz", f.get("tz"), errors, "Clinic time zone", list="tzs", required=True),
        inp("username", f.get("username"), errors, "Admin username", required=True, autocomplete="username"), D.PASSWORD_MIN,
        inp("password", "", errors, "Password", type="password", required=True, autocomplete="new-password"),
        inp("password2", "", errors, "Password again", type="password", required=True, autocomplete="new-password"))
    return page(req, "Set up FrontDesk Book", body)


@route("POST", "/setup", role="public")
def setup_post(req):
    if req.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        raise Redirect("/login")
    f = req.fdict()
    try:
        uid = D.create_first_admin(req.conn, f.get("clinic_name"), f.get("tz"), f.get("username"), f.get("password"), f.get("password2"))
    except ValidationError as ex:
        return setup_get(req, ex.errors, f)
    except Conflict:
        raise Redirect("/login")
    start_session(req, uid)
    raise Redirect("/day", "Welcome! Your clinic is set up.")


def start_session(req, uid):
    token = secrets.token_urlsafe(32)
    with db.tx(req.conn):
        req.conn.execute("INSERT INTO sessions(token,user_id,created_at,last_seen) VALUES(?,?,?,?)", (token, uid, D.to_s(req.now), D.to_s(req.now)))
    req.token = token
    req.set_cookie = "fd_session=%s; HttpOnly; SameSite=Strict; Path=/" % token


@route("GET", "/login", role="public")
def login_get(req, error=None, username=""):
    if not req.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        raise Redirect("/setup")
    body = """<div class="card">%s<form method="post">%s%s%s<p><button class="primary">Sign in</button></p></form></div>""" % (
        '<div class="errbox">%s</div>' % e(error) if error else "", hidden(req),
        inp("username", username, None, "Username", required=True, autofocus=True, autocomplete="username"),
        inp("password", "", None, "Password", type="password", required=True, autocomplete="current-password"))
    return page(req, "Sign in", body)


@route("POST", "/login", role="public")
def login_post(req):
    try:
        u = D.authenticate(req.conn, req.f("username"), req.f("password"), req.now)
    except ValidationError as ex:
        return login_get(req, str(ex), req.f("username"))
    start_session(req, u["id"])
    raise Redirect("/password" if u["must_change"] else "/day")


@route("POST", "/logout", role="any")
def logout(req):
    with db.tx(req.conn):
        req.conn.execute("DELETE FROM sessions WHERE token=?", (req.token,))
    req.set_cookie = "fd_session=; Max-Age=0; Path=/"
    raise Redirect("/login")


@route("GET", "/password", role="any")
def password_get(req, errors=None):
    note = '<div class="warnbox">You must choose a new password before continuing.</div>' if req.user["must_change"] else ""
    body = '<div class="card">%s%s<form method="post">%s%s%s%s<p><button class="primary">Change password</button></p></form></div>' % (
        note, errbox(errors, ("current", "password", "password2")), hidden(req),
        inp("current", "", errors, "Current password", type="password", required=True),
        inp("password", "", errors, "New password (at least %d characters)" % D.PASSWORD_MIN, type="password", required=True),
        inp("password2", "", errors, "New password again", type="password", required=True))
    return page(req, "Change password", body)


@route("POST", "/password", role="any")
def password_post(req):
    try:
        D.change_own_password(req.conn, req.user, req.f("current"), req.f("password"), req.f("password2"), req.now,
                                keep_token=req.token)
    except ValidationError as ex:
        return password_get(req, ex.errors)
    raise Redirect("/day", "Password changed.")


# ------------------------------------------------------------------ day & week views
def practitioners(conn, include_archived=False):
    return conn.execute("SELECT * FROM practitioners %s ORDER BY name" % ("" if include_archived else "WHERE archived=0")).fetchall()


def render_column(req, pr, d, appts, head, view_s, view_e):
    tz = req.tz
    h = (view_e - view_s) * PX
    parts = []
    for s, en in D.hours_for(req.conn, pr["id"])[d.weekday()]:
        s2, e2 = max(s, view_s), min(en, view_e)
        if e2 > s2:
            parts.append('<div class="hrs" style="top:%dpx;height:%dpx"></div>' % ((s2 - view_s) * PX, (e2 - s2) * PX))
    for m in range(view_s - view_s % 60 + 60, view_e, 60):
        parts.append('<div class="hl" style="top:%dpx"></div>' % ((m - view_s) * PX))
    for t in D.timeoff_for(req.conn, pr["id"], d, d):
        s, en = (view_s, view_e) if t["start_min"] is None else (max(t["start_min"], view_s), min(t["end_min"], view_e))
        if en > s:
            parts.append('<div class="off" style="top:%dpx;height:%dpx">%s</div>' % ((s - view_s) * PX, (en - s) * PX, e(t["label"])))
    if not pr["archived"]:
        floor = D.floor_grid(req.now)
        for m in range(view_s, view_e, 15):
            try:
                if D.local_to_utc(tz, d, m) < floor:
                    continue
            except ValidationError:
                continue
            parts.append('<a class="slot" title="Book %s" href="%s" style="top:%dpx;height:%dpx"></a>' % (
                D.hhmm(m), e(url("/appt/new", practitioner_id=pr["id"], date=d.isoformat(), time=D.hhmm(m))), (m - view_s) * PX, 15 * PX))
    if d == req.today:
        nm = D.local_minutes(tz, D.to_s(req.now), d)
        if view_s <= nm <= view_e:
            parts.append('<div class="nowline" style="top:%dpx"></div>' % ((nm - view_s) * PX))
    cancelled = []
    for a, r in appts:
        if a["status"] == "cancelled":
            cancelled.append('<div><a href="/appt/%d">%s %s %s</a>%s</div>' % (
                a["id"], D.local(tz, a["start_utc"]).strftime("%H:%M"), e(a["first_name"]), e(a["last_name"]), " (late)" if a["late_cancel"] else ""))
            continue
        s = D.local_minutes(tz, a["start_utc"], d)
        en = D.local_minutes(tz, a["end_utc"], d)
        top, ht = (s - view_s) * PX, max((min(en, view_e) - s) * PX, 16)
        flag = ""
        if a["status"] == "booked" and D.outside_hours_reason(req.conn, tz, a["practitioner_id"], a["start_utc"], a["end_utc"]):
            flag = ' <span class="flag">outside hours</span>'
        quick = ""
        if a["status"] == "booked" and req.now >= D.from_s(a["start_utc"]):
            quick = "<br>" + post_button(req, "/appt/%d/status" % a["id"], "Attended", {"status": "attended", "version": a["version"], "back": req.path + "?" + urllib.parse.urlencode(req.query, doseq=True)}) + \
                    post_button(req, "/appt/%d/status" % a["id"], "No-show", {"status": "no_show", "version": a["version"], "back": req.path + "?" + urllib.parse.urlencode(req.query, doseq=True)})
        parts.append('<div class="ap %s" style="top:%dpx;height:%dpx;border-color:%s" title="%s"><a href="/appt/%d" style="color:inherit;text-decoration:none">'
                     '<b>%s–%s %s %s</b><br>%s &middot; <span class="st-%s">%s</span> &middot; %s%s</a>%s</div>' % (
                         a["status"], top, ht, e(pr["colour"]), e(D.reminder_text(tz, r)), a["id"],
                         D.local(tz, a["start_utc"]).strftime("%H:%M"), D.local(tz, a["end_utc"]).strftime("%H:%M"),
                         e(a["first_name"]), e(a["last_name"]), e(a["type_name"]), a["status"], D.STATUS_LABEL[a["status"]],
                         e(D.reminder_text(tz, r)), flag, quick))
    return ('<div class="col"><div class="colhead" style="border-color:%s">%s</div><div class="colbody" style="height:%dpx">%s</div>'
            '<div class="cx">%s</div></div>') % (e(pr["colour"]), head, h, "".join(parts),
                                                 ("Cancelled:" + "".join(cancelled)) if cancelled else "")


def view_range(req, appts_by_day):
    s, en = D.DAY_START, D.DAY_END
    for d, appts in appts_by_day:
        for a, _ in appts:
            if a["status"] != "cancelled":
                s = min(s, D.local_minutes(req.tz, a["start_utc"], d) // 60 * 60)
                en = max(en, min(1440, -(-D.local_minutes(req.tz, a["end_utc"], d) // 60) * 60))
    return s, en


def axis(view_s, view_e):
    marks = "".join('<div style="top:%dpx">%s</div>' % ((m - view_s) * PX, D.hhmm(m)) for m in range(view_s, view_e + 1, 60))
    return '<div class="axis"><div class="colhead" style="position:static;border-color:transparent;background:none">&nbsp;</div>' \
           '<div style="position:relative;height:%dpx">%s</div></div>' % ((view_e - view_s) * PX, marks)


@route("GET", "/")
def home(req):
    raise Redirect("/day")


@route("GET", "/day")
def day_view(req):
    d = parse_day(req)
    prs = practitioners(req.conn)
    chosen = [int(x) for x in req.query.get("p", []) if x.isdigit()]
    shown = [p for p in prs if not chosen or p["id"] in chosen]
    data = [(p, [x for x in D.appts_in_range(req.conn, d, d, [p["id"]])]) for p in shown]
    vs, ve = view_range(req, [(d, a) for _, a in data])
    cols = "".join(render_column(req, p, d, a, e((p["title"] + " " + p["name"]).strip()), vs, ve) for p, a in data)
    filt = "".join('<label style="display:inline;font-weight:normal;margin-right:8px"><input type="checkbox" name="p" value="%d"%s> %s</label>' % (
        p["id"], " checked" if p["id"] in chosen else "", e(p["name"])) for p in prs)
    nav = ('<div class="noprint row" style="align-items:center;margin-bottom:10px"><a class="btn" href="%s">&larr; Previous</a>'
           '<a class="btn" href="%s">Today</a><a class="btn" href="%s">Next &rarr;</a>'
           '<form method="get" class="inline"><input type="date" name="date" value="%s"> %s <button>Show</button></form>'
           '<a class="btn" href="%s">New appointment</a><a class="btn" href="%s">Day sheet</a></div>') % (
        e(url("/day", date=(d - dt.timedelta(days=1)).isoformat(), p=chosen)), e(url("/day", p=chosen)),
        e(url("/day", date=(d + dt.timedelta(days=1)).isoformat(), p=chosen)), d.isoformat(), filt,
        e(url("/appt/new", date=d.isoformat())), e(url("/daysheet", date=d.isoformat(), p=chosen)))
    checklist = ""
    if req.is_admin:
        n_pr = len(prs)
        n_ty = req.conn.execute("SELECT COUNT(*) FROM appt_types WHERE archived=0").fetchone()[0]
        hours_set = req.conn.execute("SELECT COUNT(*) FROM audit_log WHERE detail LIKE 'set working hours%'").fetchone()[0]
        mail_ok = mailer.is_configured(mailer.effective(req.conn, req.app.cfg))
        items = [(n_pr, "/admin/practitioners", "Add practitioners"), (hours_set or (n_pr and req.conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]), "/admin/practitioners", "Set working hours"),
                 (n_ty, "/admin/types", "Add appointment types"), (mail_ok, "/admin/email", "Configure email")]
        if not all(i[0] for i in items):
            checklist = '<div class="card noprint"><b>Getting started</b><ul class="checklist">%s</ul></div>' % "".join(
                '<li class="%s">%s <a href="%s">%s</a></li>' % ("done" if ok else "", "✓" if ok else "☐", u, t) for ok, u, t in items)
    if not shown:
        cols = '<p class="muted">No practitioners yet.</p>'
    body = checklist + nav + '<div class="grid">%s%s</div>' % (axis(vs, ve) if shown else "", cols)
    return page(req, D.fmt_date(d), body)


@route("GET", "/week")
def week_view(req):
    d = parse_day(req)
    prs = practitioners(req.conn)
    if not prs:
        return page(req, "Week", '<p class="muted">No practitioners yet.</p>')
    pid = int(req.q("pr")) if req.q("pr").isdigit() else prs[0]["id"]
    pr = req.conn.execute("SELECT * FROM practitioners WHERE id=?", (pid,)).fetchone() or prs[0]
    monday = d - dt.timedelta(days=d.weekday())
    days = [monday + dt.timedelta(days=i) for i in range(7)]
    data = [(x, D.appts_in_range(req.conn, x, x, [pr["id"]])) for x in days]
    vs, ve = view_range(req, data)
    cols = "".join(render_column(req, pr, x, a, '<a href="%s">%s</a>' % (e(url("/day", date=x.isoformat())), e(D.fmt_date(x)[:-5])), vs, ve)
                   for x, a in data)
    nav = ('<div class="noprint row" style="align-items:center;margin-bottom:10px"><a class="btn" href="%s">&larr; Previous week</a>'
           '<a class="btn" href="%s">This week</a><a class="btn" href="%s">Next week &rarr;</a>'
           '<form method="get" class="inline">%s <input type="date" name="date" value="%s"> <button>Show</button></form></div>') % (
        e(url("/week", pr=pr["id"], date=(monday - dt.timedelta(days=7)).isoformat())), e(url("/week", pr=pr["id"])),
        e(url("/week", pr=pr["id"], date=(monday + dt.timedelta(days=7)).isoformat())),
        select("pr", [(p["id"], p["name"]) for p in prs], pr["id"]), d.isoformat())
    return page(req, "Week of %s – %s" % (D.fmt_date(monday), pr["name"]), nav + '<div class="grid">%s%s</div>' % (axis(vs, ve), cols))


# ------------------------------------------------------------------ booking
@route("GET", "/appt/new")
def appt_new(req, errors=None, warnings=None, conflict=None, f=None):
    f = f or {k: v[0] for k, v in req.query.items()}
    prs = practitioners(req.conn)
    types = req.conn.execute("SELECT * FROM appt_types WHERE archived=0 ORDER BY name").fetchall()
    if not prs or not types:
        return page(req, "New appointment", '<p>Add at least one practitioner and one appointment type first%s.</p>' % (
            ' (<a href="/admin">Setup</a>)' if req.is_admin else " (ask an admin)"))
    keep = {k: f.get(k, "") for k in ("practitioner_id", "date", "time", "type_id", "duration", "note")}
    patient = None
    if str(f.get("patient_id", "")).isdigit():
        patient = req.conn.execute("SELECT * FROM patients WHERE id=? AND archived=0", (int(f["patient_id"]),)).fetchone()
    if patient:
        psec = '<p><b>Patient:</b> %s %s %s &middot; %s %s <a href="%s">change</a></p>' % (
            e(patient["first_name"]), e(patient["last_name"]), e(patient["dob"] or ""), e(patient["phone"]), e(patient["email"]),
            e(url("/appt/new", **keep)))
    else:
        q = f.get("q", "")
        res = ""
        if q:
            rows = D.search_patients(req.conn, q, now=req.now, limit=20)
            res = "".join('<li><a href="%s">%s %s</a> <span class="muted">%s %s %s</span></li>' % (
                e(url("/appt/new", patient_id=r["id"], **keep)), e(r["first_name"]), e(r["last_name"]), e(r["dob"] or ""),
                e(r["phone"]), e(r["email"])) for r in rows) or "<li>No patients found.</li>"
            res = "<ul>%s</ul>" % res
        here = url("/appt/new", **keep)
        psec = ('<form method="get">%s<label for="q">Find patient (name, phone, email or date of birth)</label>'
                '<input type="text" id="q" name="q" value="%s" autofocus> <button>Search</button> '
                '<a class="btn" href="%s">New patient</a></form>%s%s') % (
            "".join('<input type="hidden" name="%s" value="%s">' % (k, e(v)) for k, v in keep.items() if v), e(q),
            e(url("/patients/new", next=here)), res, field_err(errors, "patient_id"))
    box = ""
    if conflict:
        box += '<div class="errbox">%s</div>' % e(conflict)
    if warnings:
        box += '<div class="warnbox">%s<br>Book anyway? Press <b>Confirm and book</b>.</div>' % "<br>".join(e(w) for w in warnings)
    box += errbox(errors, ("practitioner_id", "date", "time", "type_id", "duration", "note", "patient_id"))
    tdur = {str(t["id"]): t["duration"] for t in types}
    type_id = f.get("type_id") or str(types[0]["id"])
    form = ""
    if patient:
        form = """<form method="post" action="/appt/new">%s<input type="hidden" name="patient_id" value="%d">%s
        <div class="row"><div>%s</div><div>%s</div></div>%s%s
        <label for="note">Scheduling note, no clinical information (optional, max %d)</label>
        <input type="text" id="note" name="note" maxlength="%d" value="%s">%s
        %s<p><button class="primary">%s</button> <a href="%s">Back to day</a></p></form>
        <script>var d=%s;document.getElementById('type_id').onchange=function(){document.getElementById('duration').value=d[this.value]||30}</script>""" % (
            hidden(req), patient["id"], select("practitioner_id", [(p["id"], (p["title"] + " " + p["name"]).strip()) for p in prs],
                                              f.get("practitioner_id"), errors, "Practitioner"),
            inp("date", f.get("date") or req.today.isoformat(), errors, "Date", type="date", required=True),
            inp("time", f.get("time"), errors, "Start time", type="time", step=300, required=True),
            select("type_id", [(t["id"], "%s (%d min)" % (t["name"], t["duration"])) for t in types], type_id, errors, "Appointment type"),
            inp("duration", f.get("duration") or tdur.get(type_id, 30), errors, "Duration (minutes, 5-minute steps)", type="number",
                min=D.MIN_DURATION, max=D.MAX_DURATION, step=5),
            D.NOTE_MAX, D.NOTE_MAX, e(f.get("note", "")), field_err(errors, "note"),
            '<input type="hidden" name="confirm" value="1">' if warnings else "",
            "Confirm and book" if warnings else "Book appointment", e(url("/day", date=f.get("date"))), json.dumps(tdur))
    return page(req, "New appointment", box + '<div class="card">%s%s</div>' % (psec, form))


@route("POST", "/appt/new")
def appt_create(req):
    f = req.fdict()
    try:
        aid = D.book(req.conn, req.user, f, confirm=f.get("confirm") == "1", now=req.now)
    except NeedsConfirm as ex:
        return appt_new(req, warnings=ex.warnings, f=f)
    except Conflict as ex:
        return appt_new(req, conflict=str(ex) + ". Nothing was saved. Another booking may have just taken this slot: check the day view.", f=f)
    except ValidationError as ex:
        return appt_new(req, errors=ex.errors, f=f)
    r = D.current_reminder(req.conn, aid)
    raise Redirect("/appt/%d" % aid, "Appointment booked. %s." % D.reminder_text(req.tz, r))


# ------------------------------------------------------------------ appointment page
def history_rows(req, aid):
    rows = req.conn.execute("SELECT h.*, u.username FROM appt_history h LEFT JOIN users u ON u.id=h.user_id WHERE appointment_id=? ORDER BY h.id",
                            (aid,)).fetchall()
    out = []
    for h in rows:
        det = json.loads(h["details"] or "{}")
        txt = "; ".join("%s: %s" % (k, v) for k, v in det.items())
        out.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (e(D.fmt_dt(req.tz, h["at"])), e(h["username"] or "system"),
                                                                             e(h["action"]), e(txt)))
    return "<table><tr><th>When</th><th>Who</th><th>What</th><th>Details</th></tr>%s</table>" % "".join(out)


@route("GET", r"/appt/(\d+)")
def appt_page(req, aid, errors=None, warnings=None, msg=None, f=None):
    try:
        a = D.get_appt(req.conn, int(aid))
    except NotFound:
        raise HTTPError(404, "Appointment not found.")
    tz = req.tz
    r = D.current_reminder(req.conn, a["id"])
    ls, le = D.local(tz, a["start_utc"]), D.local(tz, a["end_utc"])
    info = """<table><tr><th>Patient</th><td><a href="/patients/%d">%s %s</a> &middot; %s %s</td></tr>
    <tr><th>When</th><td>%s, %s–%s (%d min)</td></tr><tr><th>Practitioner</th><td>%s</td></tr><tr><th>Type</th><td>%s</td></tr>
    <tr><th>Status</th><td class="st-%s">%s%s</td></tr><tr><th>Scheduling note</th><td>%s</td></tr><tr><th>Reminder</th><td>%s</td></tr>
    <tr><th>Booked by</th><td>%s, %s</td></tr></table>""" % (
        a["patient_id"], e(a["first_name"]), e(a["last_name"]), e(a["phone"]), e(a["email"]), e(D.fmt_date(ls.date())), ls.strftime("%H:%M"),
        le.strftime("%H:%M"), a["duration"], e(a["pr_name"]), e(a["type_name"]), a["status"], D.STATUS_LABEL[a["status"]],
        e(" – %s%s%s" % (D.CANCEL_REASONS.get(a["cancel_reason"], ""), ": " + a["cancel_text"] if a["cancel_text"] else "",
                              " (late cancellation)" if a["late_cancel"] else "")) if a["status"] == "cancelled" else "",
        e(a["note"]), e(D.reminder_text(tz, r)), e(D.username_of(req.conn, a["created_by"])), e(D.fmt_dt(tz, a["created_at"])))
    actions = []
    box = ""
    if msg:
        box += '<div class="errbox">%s</div>' % e(msg)
    if warnings:
        box += '<div class="warnbox">%s<br>Move anyway? Press <b>Confirm move</b>.</div>' % "<br>".join(e(w) for w in warnings)
    box += errbox(errors, ("date", "time", "duration", "practitioner_id", "reason", "text"))
    v = {"version": a["version"]}
    if a["status"] == "booked":
        f = f or {"date": ls.date().isoformat(), "time": ls.strftime("%H:%M"), "duration": a["duration"], "practitioner_id": a["practitioner_id"]}
        actions.append("""<div class="card"><h2>Move</h2><form method="post" action="/appt/%d/move">%s<input type="hidden" name="version" value="%d">
        <div class="row"><div>%s</div><div>%s</div><div>%s</div><div>%s</div></div>%s<p><button class="primary">%s</button></p></form></div>""" % (
            a["id"], hidden(req), a["version"], inp("date", f.get("date"), errors, "Date", type="date"),
            inp("time", f.get("time"), errors, "Start time", type="time", step=300),
            inp("duration", f.get("duration"), errors, "Duration (min)", type="number", min=5, max=480, step=5),
            select("practitioner_id", [(p["id"], p["name"]) for p in practitioners(req.conn)], f.get("practitioner_id"), errors, "Practitioner"),
            '<input type="hidden" name="confirm" value="1">' if warnings else "", "Confirm move" if warnings else "Move"))
        actions.append("""<div class="card"><h2>Cancel</h2><form method="post" action="/appt/%d/cancel">%s<input type="hidden" name="version" value="%d">
        %s<label for="text">Short text (required for Other)</label><input type="text" id="text" name="text" maxlength="100">%s
        <p><button class="danger">Cancel appointment</button></p></form></div>""" % (
            a["id"], hidden(req), a["version"], select("reason", [("", "Choose…")] + list(D.CANCEL_REASONS.items()), "", errors, "Reason"),
            field_err(errors, "text")))
        if req.now >= D.from_s(a["start_utc"]):
            actions.append('<div class="card"><h2>Close</h2>%s %s</div>' % (
                post_button(req, "/appt/%d/status" % a["id"], "Attended", dict(v, status="attended")),
                post_button(req, "/appt/%d/status" % a["id"], "No-show", dict(v, status="no_show"))))
        elif a["email"]:
            actions.append('<div class="card"><h2>Reminder</h2>%s</div>' % post_button(
                req, "/appt/%d/resend" % a["id"], "Resend reminder now", confirm="Send the reminder email again now?"))
    elif req.now < D.undo_deadline(tz, a):
        actions.append('<div class="card"><h2>Undo</h2><p>Return this appointment to Booked.</p>%s</div>' % post_button(
            req, "/appt/%d/undo" % a["id"], "Undo (%s → Booked)" % D.STATUS_LABEL[a["status"]], v))
    log_rows = req.conn.execute("SELECT * FROM email_log WHERE appointment_id=? ORDER BY id", (a["id"],)).fetchall()
    sends = "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
        e(D.fmt_dt(tz, x["at"])), e(x["kind"]), e(x["recipient"]), e(x["result"]), e(x["error"])) for x in log_rows)
    body = box + '<div class="row"><div class="card">%s<p><a href="%s">Show on day view</a></p></div><div>%s</div></div>' % (
        info, e(url("/day", date=ls.date().isoformat())), "".join(actions))
    body += "<h2>History</h2>" + history_rows(req, a["id"])
    if sends:
        body += "<h2>Emails</h2><table><tr><th>When</th><th>Kind</th><th>To</th><th>Result</th><th>Error</th></tr>%s</table>" % sends
    return page(req, "Appointment: %s %s" % (a["first_name"], a["last_name"]), body)


def _appt_action(req, aid, fn, okmsg, back=None):
    try:
        fn()
    except Stale as ex:
        return appt_page(req, aid, msg=str(ex))
    except (Conflict, NotFound) as ex:
        return appt_page(req, aid, msg=str(ex))
    except ValidationError as ex:
        if back:
            raise Redirect(back, str(ex))
        return appt_page(req, aid, errors=ex.errors)
    raise Redirect(back or "/appt/%s" % aid, okmsg)


@route("POST", r"/appt/(\d+)/move")
def appt_move(req, aid):
    f = req.fdict()
    try:
        D.move(req.conn, req.user, int(aid), f, confirm=f.get("confirm") == "1", now=req.now)
    except NeedsConfirm as ex:
        return appt_page(req, aid, warnings=ex.warnings, f=f)
    except (Stale, Conflict, NotFound) as ex:
        return appt_page(req, aid, msg=str(ex), f=f)
    except ValidationError as ex:
        return appt_page(req, aid, errors=ex.errors, f=f)
    raise Redirect("/appt/%s" % aid, "Appointment moved. %s." % D.reminder_text(req.tz, D.current_reminder(req.conn, int(aid))))


@route("POST", r"/appt/(\d+)/cancel")
def appt_cancel(req, aid):
    return _appt_action(req, aid, lambda: D.cancel(req.conn, req.user, int(aid), req.f("reason"), req.f("text"), req.f("version"), req.now),
                        "Appointment cancelled.")


@route("POST", r"/appt/(\d+)/status")
def appt_status(req, aid):
    back = req.f("back") if req.f("back").startswith("/") and not req.f("back").startswith("//") else None
    return _appt_action(req, aid, lambda: D.set_status(req.conn, req.user, int(aid), req.f("status"), req.f("version"), req.now),
                        "Marked %s." % D.STATUS_LABEL.get(req.f("status"), ""), back)


@route("POST", r"/appt/(\d+)/undo")
def appt_undo(req, aid):
    return _appt_action(req, aid, lambda: D.undo(req.conn, req.user, int(aid), req.f("version"), req.now), "Returned to Booked.")


@route("POST", r"/appt/(\d+)/resend")
def appt_resend(req, aid):
    def go():
        D.resend_reminder(req.conn, req.user, int(aid), req.now)
        req.app.wake.set()
    return _appt_action(req, aid, go, "Reminder queued to send now.")


# ------------------------------------------------------------------ patients
def patient_form(req, f, errors, action, button, extra=""):
    return """<form method="post" action="%s">%s%s<div class="row"><div>%s</div><div>%s</div></div>%s
    <div class="row"><div>%s</div><div>%s</div></div><label><input type="checkbox" name="send_reminders" value="1"%s> Send reminders</label>
    <p class="muted">At least one of phone or email is required.</p><p><button class="primary">%s</button></p></form>""" % (
        e(action), hidden(req), extra, inp("first_name", f.get("first_name"), errors, "First name", maxlength=100, required=True),
        inp("last_name", f.get("last_name"), errors, "Last name", maxlength=100, required=True),
        inp("dob", f.get("dob") or "", errors, "Date of birth", type="date", max=req.today.isoformat()),
        inp("phone", f.get("phone"), errors, "Mobile phone", type="tel"), inp("email", f.get("email"), errors, "Email", type="email"),
        " checked" if f.get("send_reminders") in ("1", 1, "on", True) else "", e(button))


def safe_next(n):
    return n if n.startswith("/") and not n.startswith("//") else ""


@route("GET", "/patients")
def patients_list(req):
    q = req.q("q")
    arch = req.q("archived") == "1"
    rows = D.search_patients(req.conn, q, arch, req.now)
    tz = req.tz
    trs = "".join('<tr><td><a href="/patients/%d">%s %s</a>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
        r["id"], e(r["last_name"]), e(r["first_name"]), " <i>(archived)</i>" if r["archived"] else "", e(r["dob"] or ""), e(r["phone"]),
        e(r["email"]), e(D.fmt_dt(tz, r["next_start"]) if r["next_start"] else "")) for r in rows)
    body = ('<form method="get" class="noprint"><input type="text" name="q" value="%s" placeholder="Name, phone, email or date of birth" autofocus> '
            '<label style="display:inline;font-weight:normal"><input type="checkbox" name="archived" value="1"%s> include archived</label> '
            '<button>Search</button> <a class="btn" href="/patients/new">Add patient</a></form><p class="muted">%d shown%s</p>'
            '<table><tr><th>Name</th><th>Date of birth</th><th>Phone</th><th>Email</th><th>Next appointment</th></tr>%s</table>') % (
        e(q), " checked" if arch else "", len(rows), " (first 100)" if len(rows) == 100 else "", trs)
    return page(req, "Patients", body)


@route("GET", "/patients/new")
def patient_new(req, errors=None, f=None, dups=None):
    f = f or {"send_reminders": "1" if D.get_setting(req.conn, "patients.reminder_default") == "on" else "0"}
    nxt = safe_next(req.q("next") or (f.get("next") or ""))
    box = errbox(errors, ("first_name", "last_name", "dob", "phone", "email"))
    if dups:
        items = "".join('<li>%s %s %s %s %s%s – <a class="btn" href="%s">Use existing</a></li>' % (
            e(d["first_name"]), e(d["last_name"]), e(d["dob"] or ""), e(d["phone"]), e(d["email"]), " (archived)" if d["archived"] else "",
            e((nxt + ("&" if "?" in nxt else "?") + "patient_id=%d" % d["id"]) if nxt and not d["archived"] else "/patients/%d" % d["id"]))
            for d in dups)
        box += '<div class="warnbox"><b>Possible duplicate.</b> These patients look similar:<ul>%s</ul>If this is a different person, press <b>Create anyway</b>.</div>' % items
    extra = '<input type="hidden" name="next" value="%s">' % e(nxt) + ('<input type="hidden" name="force" value="1">' if dups else "")
    return page(req, "Add patient", box + '<div class="card">%s</div>' % patient_form(req, f, errors, "/patients/new",
                                                                                     "Create anyway" if dups else "Add patient", extra))


@route("POST", "/patients/new")
def patient_create(req):
    f = req.fdict()
    try:
        pid = D.create_patient(req.conn, req.user, f, force=f.get("force") == "1", now=req.now)
    except NeedsConfirm as ex:
        return patient_new(req, f=f, dups=ex.warnings)
    except ValidationError as ex:
        return patient_new(req, errors=ex.errors, f=f)
    nxt = safe_next(f.get("next", ""))
    if nxt:
        raise Redirect(nxt + ("&" if "?" in nxt else "?") + "patient_id=%d" % pid, "Patient added.")
    raise Redirect("/patients/%d" % pid, "Patient added.")


@route("GET", r"/patients/(\d+)")
def patient_page(req, pid, errors=None, f=None, msg=None):
    try:
        p = D.get_patient(req.conn, int(pid))
    except NotFound:
        raise Redirect("/patients", "Patient not found.")
    tz = req.tz
    rows = req.conn.execute(D.APPT_SELECT + " WHERE a.patient_id=? ORDER BY a.start_utc DESC", (p["id"],)).fetchall()
    fut = [a for a in rows if D.from_s(a["start_utc"]) >= req.now]
    past = [a for a in rows if D.from_s(a["start_utc"]) < req.now]

    def tbl(lst):
        if not lst:
            return '<p class="muted">None.</p>'
        return "<table><tr><th>When</th><th>Practitioner</th><th>Type</th><th>Status</th></tr>%s</table>" % "".join(
            '<tr><td><a href="/appt/%d">%s</a></td><td>%s</td><td>%s</td><td class="st-%s">%s</td></tr>' % (
                a["id"], e(D.fmt_dt(tz, a["start_utc"])), e(a["pr_name"]), e(a["type_name"]), a["status"], D.STATUS_LABEL[a["status"]]) for a in lst)
    box = ('<div class="errbox">%s</div>' % e(msg) if msg else "") + errbox(errors, ("first_name", "last_name", "dob", "phone", "email"))
    if p["archived"]:
        actions = '<div class="warnbox">This patient is archived. %s</div>' % post_button(req, "/patients/%d/archive" % p["id"], "Restore",
                                                                                           {"archived": "0", "version": p["version"]})
        form = ""
    else:
        actions = '<p><a class="btn" href="%s">Book appointment</a> %s</p>' % (
            e(url("/appt/new", patient_id=p["id"])),
            post_button(req, "/patients/%d/archive" % p["id"], "Archive patient", {"archived": "1", "version": p["version"]},
                        confirm="Archive this patient?"))
        form = '<div class="card"><h2>Details</h2>%s</div>' % patient_form(
            req, f or dict(p), errors, "/patients/%d" % p["id"], "Save changes", '<input type="hidden" name="version" value="%d">' % p["version"])
    body = box + actions + '<div class="row">%s<div><h2>Upcoming</h2>%s<h2>Past</h2>%s</div></div>' % (form, tbl(fut[::-1]), tbl(past))
    return page(req, "%s %s" % (p["first_name"], p["last_name"]), body)


@route("POST", r"/patients/(\d+)")
def patient_update(req, pid):
    f = req.fdict()
    try:
        D.update_patient(req.conn, req.user, int(pid), f, req.now)
    except NotFound as ex:
        raise Redirect("/patients", str(ex))
    except Stale as ex:
        return patient_page(req, pid, msg=str(ex))
    except ValidationError as ex:
        return patient_page(req, pid, errors=ex.errors, f=f)
    raise Redirect("/patients/%s" % pid, "Patient saved.")


@route("POST", r"/patients/(\d+)/archive")
def patient_archive(req, pid):
    arch = req.f("archived") == "1"
    try:
        D.archive_patient(req.conn, req.user, int(pid), arch, req.f("version"), req.now)
    except NeedsConfirm as ex:
        return patient_page(req, pid, msg="Cannot archive: cancel or move these future appointments first: " + "; ".join(ex.warnings))
    except (Stale, NotFound) as ex:
        return patient_page(req, pid, msg=str(ex))
    raise Redirect("/patients/%s" % pid, "Patient archived." if arch else "Patient restored.")


# ------------------------------------------------------------------ reminders page
@route("GET", "/reminders")
def reminders_page(req):
    tz = req.tz
    now_s = D.to_s(req.now)
    upcoming = req.conn.execute(D.APPT_SELECT + " WHERE a.status='booked' AND a.start_utc>=? AND a.start_utc<? ORDER BY a.start_utc",
                                (now_s, D.to_s(req.now + dt.timedelta(days=2)))).fetchall()
    trs = []
    for a in upcoming:
        r = D.current_reminder(req.conn, a["id"])
        act = ""
        if r is not None and r["state"] == "failed":
            act = post_button(req, "/reminders/%d/retry" % r["id"], "Retry")
        if a["email"]:
            act += " " + post_button(req, "/appt/%d/resend" % a["id"], "Resend", confirm="Send the reminder email again now?")
        trs.append("<tr><td><a href='/appt/%d'>%s</a></td><td>%s %s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            a["id"], e(D.fmt_dt(tz, a["start_utc"])), e(a["first_name"]), e(a["last_name"]), e(a["pr_name"]),
            e(a["phone"]), e(D.reminder_text(tz, r)), act))
    fails = req.conn.execute("""SELECT r.*, p.first_name, p.last_name, p.phone, a.start_utc FROM reminders r JOIN appointments a ON a.id=r.appointment_id
                                JOIN patients p ON p.id=a.patient_id WHERE r.state='failed' AND r.created_at>=? ORDER BY r.id DESC""",
                             (D.to_s(req.now - dt.timedelta(days=7)),)).fetchall()
    ftrs = "".join("<tr><td><a href='/appt/%d'>%s</a></td><td>%s %s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
        r["appointment_id"], e(D.fmt_dt(tz, r["start_utc"])), e(r["first_name"]), e(r["last_name"]), e(r["phone"]), e(r["kind"]),
        e(r["reason"]), post_button(req, "/reminders/%d/retry" % r["id"], "Retry")) for r in fails)
    logs = req.conn.execute("SELECT l.*, u.username FROM email_log l LEFT JOIN users u ON u.id=l.user_id ORDER BY l.id DESC LIMIT 100").fetchall()
    ltrs = "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
        e(D.fmt_dt(tz, x["at"])), e(x["recipient"]), e(x["kind"]), e(x["result"]), e(x["error"]), e(x["username"] or "system")) for x in logs)
    body = ("<h2>Next 2 days</h2><table><tr><th>Appointment</th><th>Patient</th><th>Practitioner</th><th>Phone</th><th>Reminder</th><th></th></tr>%s</table>"
            "<h2>Failures in the last 7 days</h2>%s<h2>Send log (latest 100)</h2>"
            "<table><tr><th>When</th><th>To</th><th>Kind</th><th>Result</th><th>Error</th><th>By</th></tr>%s</table>") % (
        "".join(trs) or "<tr><td colspan=6 class=muted>No appointments.</td></tr>",
        ("<table><tr><th>Appointment</th><th>Patient</th><th>Phone</th><th>Kind</th><th>Error</th><th></th></tr>%s</table>" % ftrs) if ftrs
        else '<p class="muted">No failures.</p>', ltrs)
    return page(req, "Reminders", body)


@route("POST", r"/reminders/(\d+)/retry")
def reminder_retry(req, rid):
    try:
        D.retry_reminder(req.conn, req.user, int(rid), req.now)
    except (ValidationError, NotFound) as ex:
        raise Redirect("/reminders", str(ex))
    req.app.wake.set()
    raise Redirect("/reminders", "Reminder queued for retry.")


# ------------------------------------------------------------------ day sheet, summary, export
@route("GET", "/daysheet")
def daysheet(req):
    d = parse_day(req)
    prs = practitioners(req.conn, include_archived=True)
    chosen = [int(x) for x in req.query.get("p", []) if x.isdigit()]
    tz = req.tz
    sheets = []
    for p in prs:
        if chosen and p["id"] not in chosen:
            continue
        rows = D.appts_in_range(req.conn, d, d, [p["id"]])
        if p["archived"] and not rows:
            continue
        totals = {k: 0 for k in D.STATUS_LABEL}
        trs = ""
        for a, _ in rows:
            totals[a["status"]] += 1
            trs += "<tr><td>%s–%s</td><td>%s %s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                D.local(tz, a["start_utc"]).strftime("%H:%M"), D.local(tz, a["end_utc"]).strftime("%H:%M"), e(a["first_name"]),
                e(a["last_name"]), e(a["phone"]), e(a["type_name"]),
                D.STATUS_LABEL[a["status"]] + (" (late)" if a["late_cancel"] else ""))
        tot = " &middot; ".join("%s: %d" % (D.STATUS_LABEL[k], v) for k, v in totals.items())
        sheets.append('<div class="sheet"><h2>%s – %s</h2><table><tr><th>Time</th><th>Patient</th><th>Phone</th><th>Type</th><th>Status</th></tr>%s</table>'
                      '<p><b>Totals</b> – %s &middot; Total: %d</p></div>' % (
                          e((p["title"] + " " + p["name"]).strip()), e(D.fmt_date(d)), trs or "<tr><td colspan=5>No appointments.</td></tr>", tot, len(rows)))
    filt = "".join('<label style="display:inline;font-weight:normal;margin-right:8px"><input type="checkbox" name="p" value="%d"%s> %s</label>' % (
        p["id"], " checked" if p["id"] in chosen else "", e(p["name"])) for p in prs if not p["archived"])
    form = ('<form method="get" class="noprint"><input type="date" name="date" value="%s"> %s <button>Show</button> '
            '<button type="button" onclick="window.print()">Print</button></form>') % (d.isoformat(), filt)
    return page(req, "Day sheet", form + "".join(sheets))


def range_form(req, action, extra=""):
    return ('<form method="get" action="%s" class="noprint"><label style="display:inline">From</label> <input type="date" name="from" value="%s"> '
            '<label style="display:inline">To</label> <input type="date" name="to" value="%s"> <button>Show</button>%s</form>') % (
        action, e(req.q("from") or req.today.replace(day=1).isoformat()), e(req.q("to") or req.today.isoformat()), extra)


@route("GET", "/summary")
def summary_page(req):
    body = range_form(req, "/summary")
    if req.q("from"):
        try:
            d1, d2 = D.parse_range(req.fdict() or {k: v[0] for k, v in req.query.items()})
        except ValidationError as ex:
            return page(req, "Summary", body + errbox(ex.errors))
        s = D.summary(req.conn, d1, d2)
        cols = ["total", "booked", "attended", "no_show", "cancelled", "late_cancelled", "reminders_sent", "reminders_failed"]
        heads = ["Total", "Booked", "Attended", "No-show", "Cancelled", "Late cancelled", "Reminders sent", "Reminders failed"]
        if not s:
            body += '<p>No appointments.</p>'
        else:
            tot = {c: sum(v[c] for v in s.values()) for c in cols}
            body += "<table><tr><th>Practitioner</th>%s</tr>%s<tr><th>All</th>%s</tr></table>" % (
                "".join("<th>%s</th>" % h for h in heads),
                "".join("<tr><td>%s</td>%s</tr>" % (e(k), "".join("<td>%d</td>" % v[c] for c in cols)) for k, v in s.items()),
                "".join("<th>%d</th>" % tot[c] for c in cols))
        body += '<p><a href="%s">Export these appointments as CSV</a></p>' % e(url("/export", **{"from": d1.isoformat(), "to": d2.isoformat()}))
    return page(req, "Summary", body)


@route("GET", "/export")
def export_page(req):
    body = range_form(req, "/export", ' <button name="download" value="1">Download CSV</button>')
    if req.q("from"):
        try:
            d1, d2 = D.parse_range({k: v[0] for k, v in req.query.items()})
        except ValidationError as ex:
            return page(req, "Export appointments", body + errbox(ex.errors))
        rows = list(D.export_rows(req.conn, d1, d2))
        if req.q("download") == "1":
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(D.CSV_HEADER)
            w.writerows(rows)
            name = "appointments-%s-to-%s.csv" % (d1, d2)
            return 200, {"Content-Type": "text/csv; charset=utf-8", "Content-Disposition": 'attachment; filename="%s"' % name}, \
                ("﻿" + buf.getvalue()).encode()
        body += "<p>%s</p>" % ("No appointments." if not rows else "%d appointments in this range. Press Download CSV." % len(rows))
    return page(req, "Export appointments", body)


# ------------------------------------------------------------------ admin
@route("GET", "/admin", role="admin")
def admin_home(req):
    links = [("/admin/clinic", "Clinic details"), ("/admin/practitioners", "Practitioners, hours and time-off"),
             ("/admin/types", "Appointment types"), ("/admin/email", "Email sending"), ("/admin/staff", "Staff accounts"),
             ("/admin/settings", "Operator settings and audit log"), ("/admin/backup", "Backup")]
    return page(req, "Setup", "<ul>%s</ul>" % "".join('<li><a href="%s">%s</a></li>' % l for l in links))


@route("GET", "/admin/clinic", role="admin")
def clinic_get(req, errors=None, f=None, msg=None):
    c = req.conn.execute("SELECT * FROM clinic WHERE id=1").fetchone()
    f = f or dict(c)
    body = ('<div class="errbox">%s</div>' % e(msg) if msg else "") + errbox(errors, ("name", "phone", "reply_to"))
    body += """<div class="card"><p class="muted">These details appear in reminder emails. Time zone: <b>%s</b> (set at first run).</p>
    <form method="post">%s<input type="hidden" name="version" value="%s">%s<label for="address">Address</label>
    <textarea id="address" name="address" rows="3">%s</textarea>%s%s<p><button class="primary">Save</button></p></form></div>""" % (
        e(c["tz"]), hidden(req), e(c["version"]), inp("name", f.get("name"), errors, "Clinic name"), e(f.get("address")),
        inp("phone", f.get("phone"), errors, "Phone", type="tel"), inp("reply_to", f.get("reply_to"), errors, "Reply-to email", type="email"))
    return page(req, "Clinic details", body)


@route("POST", "/admin/clinic", role="admin")
def clinic_post(req):
    f = req.fdict()
    try:
        D.update_clinic(req.conn, req.user, f, req.now)
    except Stale as ex:
        return clinic_get(req, msg=str(ex))
    except ValidationError as ex:
        return clinic_get(req, ex.errors, f)
    raise Redirect("/admin/clinic", "Clinic details saved.")


@route("GET", "/admin/practitioners", role="admin")
def prs_get(req, errors=None, f=None):
    rows = practitioners(req.conn, True)
    trs = "".join('<tr><td><span style="color:%s">&#9632;</span> <a href="/admin/practitioners/%d">%s</a></td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
        e(p["colour"]), p["id"], e(p["name"]), e(p["title"]),
        e(", ".join("%s %s" % (D.WEEKDAYS[wd][:3], ",".join("%s-%s" % (D.hhmm(s), D.hhmm(x)) for s, x in rs))
                    for wd, rs in D.hours_for(req.conn, p["id"]).items() if rs)), "Archived" if p["archived"] else "Active") for p in rows)
    f = f or {}
    body = "<table><tr><th>Name</th><th>Title</th><th>Hours</th><th>State</th></tr>%s</table>" % trs
    body += """<div class="card"><h2>Add practitioner</h2>%s<form method="post">%s%s%s%s<p class="muted">New practitioners get Mon–Fri 09:00–17:00; change it on their page.</p>
    <button class="primary">Add</button></form></div>""" % (
        errbox(errors, ("name", "colour")), hidden(req), inp("name", f.get("name"), errors, "Display name", maxlength=100),
        inp("title", f.get("title"), errors, "Title (optional)", maxlength=60), inp("colour", f.get("colour", "#4a90d9"), errors, "Calendar colour", type="color"))
    return page(req, "Practitioners", body)


@route("POST", "/admin/practitioners", role="admin")
def prs_post(req):
    try:
        pid = D.save_practitioner(req.conn, req.user, req.fdict(), now=req.now)
    except ValidationError as ex:
        return prs_get(req, ex.errors, req.fdict())
    raise Redirect("/admin/practitioners/%d" % pid, "Practitioner added.")


@route("GET", r"/admin/practitioners/(\d+)", role="admin")
def pr_get(req, pid, errors=None, f=None, msg=None, warnings=None, tf=None, herr=None, hours_in=None):
    p = req.conn.execute("SELECT * FROM practitioners WHERE id=?", (int(pid),)).fetchone()
    if not p:
        raise HTTPError(404, "No such practitioner.")
    f = f or dict(p)
    hrs = D.hours_for(req.conn, p["id"])
    hours_in = hours_in or {wd: ", ".join("%s-%s" % (D.hhmm(s), D.hhmm(x)) for s, x in hrs[wd]) for wd in range(7)}
    hform = "".join('<div>%s</div>' % inp("day%d" % wd, hours_in.get(wd, ""), herr, D.WEEKDAYS[wd], placeholder="e.g. 09:00-12:30, 13:30-17:00")
                    for wd in range(7))
    tz = req.tz
    toffs = req.conn.execute("SELECT * FROM timeoff WHERE practitioner_id=? AND end_date>=? ORDER BY start_date", (p["id"], (req.today - dt.timedelta(days=30)).isoformat())).fetchall()
    ttrs = "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
        e(t["start_date"] + ("" if t["end_date"] == t["start_date"] else " to " + t["end_date"])),
        "All day" if t["start_min"] is None else "%s–%s" % (D.hhmm(t["start_min"]), D.hhmm(t["end_min"])), e(t["label"]),
        post_button(req, "/admin/timeoff/%d/delete" % t["id"], "Remove", {"pid": p["id"]})) for t in toffs)
    tf = tf or {}
    box = ('<div class="errbox">%s</div>' % e(msg) if msg else "")
    twarn = ""
    if warnings:
        twarn = ('<div class="warnbox">These booked appointments fall in the time-off. They stay booked and will be flagged "outside hours":<ul>%s</ul>'
                 'Press <b>Confirm and save</b> to add the time-off anyway.</div>') % "".join("<li>%s</li>" % e(w) for w in warnings)
    arch = post_button(req, "/admin/practitioners/%d/archive" % p["id"], "Restore" if p["archived"] else "Archive practitioner",
                       {"archived": "0" if p["archived"] else "1"})
    body = box + """<div class="row"><div class="card"><h2>Details</h2>%s<form method="post">%s<input type="hidden" name="version" value="%d">%s%s%s
    <p><button class="primary">Save</button></p></form><p>%s</p></div>
    <div class="card"><h2>Weekly working hours</h2><form method="post" action="/admin/practitioners/%d/hours">%s%s
    <p class="muted">One or more ranges per day, separated by commas. Leave empty for a day off.</p><button class="primary">Save hours</button></form></div></div>
    <div class="card"><h2>Time-off</h2><table><tr><th>Dates</th><th>Hours</th><th>Label</th><th></th></tr>%s</table>
    <h2>Add time-off</h2>%s%s<form method="post" action="/admin/practitioners/%d/timeoff">%s<div class="row"><div>%s</div><div>%s</div><div>%s</div><div>%s</div><div>%s</div></div>
    <p class="muted">Leave the times empty for whole days.</p>%s<button class="primary">%s</button></form></div>""" % (
        errbox(errors, ("name", "colour")), hidden(req), p["version"], inp("name", f.get("name"), errors, "Display name", maxlength=100),
        inp("title", f.get("title"), errors, "Title", maxlength=60), inp("colour", f.get("colour"), errors, "Calendar colour", type="color"),
        arch, p["id"], hidden(req), hform, ttrs or "<tr><td colspan=4 class=muted>None.</td></tr>",
        errbox(herr if False else None), twarn, p["id"], hidden(req),
        inp("start_date", tf.get("start_date"), errors, "From", type="date", required=True), inp("end_date", tf.get("end_date"), errors, "To", type="date"),
        inp("start_time", tf.get("start_time"), errors, "Start time", type="time", step=300), inp("end_time", tf.get("end_time"), errors, "End time", type="time", step=300),
        inp("label", tf.get("label", "Leave"), errors, "Label", maxlength=40), '<input type="hidden" name="confirm" value="1">' if warnings else "",
        "Confirm and save" if warnings else "Add time-off")
    return page(req, "Practitioner: %s%s" % (p["name"], " (archived)" if p["archived"] else ""), body)


@route("POST", r"/admin/practitioners/(\d+)", role="admin")
def pr_post(req, pid):
    try:
        D.save_practitioner(req.conn, req.user, req.fdict(), int(pid), req.now)
    except Stale as ex:
        return pr_get(req, pid, msg=str(ex))
    except ValidationError as ex:
        return pr_get(req, pid, errors=ex.errors, f=req.fdict())
    raise Redirect("/admin/practitioners/%s" % pid, "Saved.")


@route("POST", r"/admin/practitioners/(\d+)/hours", role="admin")
def pr_hours(req, pid):
    data = {wd: req.f("day%d" % wd) for wd in range(7)}
    try:
        D.set_hours(req.conn, req.user, int(pid), data, req.now)
    except ValidationError as ex:
        return pr_get(req, pid, herr=ex.errors, hours_in=data, msg="Hours not saved: " + " ".join(ex.errors.values()))
    raise Redirect("/admin/practitioners/%s" % pid, "Working hours saved.")


@route("POST", r"/admin/practitioners/(\d+)/timeoff", role="admin")
def pr_timeoff(req, pid):
    f = req.fdict()
    try:
        D.add_timeoff(req.conn, req.user, int(pid), f, confirm=f.get("confirm") == "1", now=req.now)
    except NeedsConfirm as ex:
        return pr_get(req, pid, warnings=ex.warnings, tf=f)
    except ValidationError as ex:
        return pr_get(req, pid, errors=ex.errors, tf=f, msg="Time-off not saved: " + " ".join(ex.errors.values()))
    raise Redirect("/admin/practitioners/%s" % pid, "Time-off added.")


@route("POST", r"/admin/timeoff/(\d+)/delete", role="admin")
def timeoff_delete(req, tid):
    D.delete_timeoff(req.conn, req.user, int(tid), req.now)
    raise Redirect("/admin/practitioners/%s" % req.f("pid"), "Time-off removed.")


@route("POST", r"/admin/practitioners/(\d+)/archive", role="admin")
def pr_archive(req, pid):
    try:
        D.archive_practitioner(req.conn, req.user, int(pid), req.f("archived") == "1", req.now)
    except NeedsConfirm as ex:
        return pr_get(req, pid, msg="Cannot archive: move or cancel these future appointments first: " + "; ".join(ex.warnings))
    raise Redirect("/admin/practitioners/%s" % pid, "Saved.")


@route("GET", "/admin/types", role="admin")
def types_get(req, errors=None, msg=None):
    rows = req.conn.execute("SELECT t.*, (SELECT COUNT(*) FROM appointments a WHERE a.type_id=t.id) AS used FROM appt_types t ORDER BY archived, name").fetchall()
    trs = "".join("""<tr><td><form class="inline" method="post" action="/admin/types/%d">%s<input type="hidden" name="version" value="%d">
    <input type="text" name="name" value="%s" maxlength="100" style="width:200px"> <input type="number" name="duration" value="%d" min="5" max="480" step="5" style="width:70px"> min
    <button>Save</button></form></td><td>%s</td><td>%s %s</td></tr>""" % (
        t["id"], hidden(req), t["version"], e(t["name"]), t["duration"], "Archived" if t["archived"] else "Active",
        post_button(req, "/admin/types/%d/archive" % t["id"], "Restore" if t["archived"] else "Archive", {"archived": "0" if t["archived"] else "1"}),
        "" if t["used"] else post_button(req, "/admin/types/%d/delete" % t["id"], "Delete", cls="danger", confirm="Delete this unused type?"))
        for t in rows)
    body = ('<div class="errbox">%s</div>' % e(msg) if msg else "") + errbox(errors, ())
    body += "<table><tr><th>Name and default duration</th><th>State</th><th></th></tr>%s</table>" % trs
    body += '<div class="card"><h2>Add type</h2><form method="post" action="/admin/types">%s%s%s<p><button class="primary">Add</button></p></form></div>' % (
        hidden(req), inp("name", "", errors, "Name", maxlength=100), inp("duration", "30", errors, "Default duration (minutes)", type="number", min=5, max=480, step=5))
    return page(req, "Appointment types", body)


@route("POST", "/admin/types", role="admin")
def types_post(req):
    try:
        D.save_type(req.conn, req.user, req.fdict(), now=req.now)
    except ValidationError as ex:
        return types_get(req, ex.errors)
    raise Redirect("/admin/types", "Type added.")


@route("POST", r"/admin/types/(\d+)", role="admin")
def type_post(req, tid):
    try:
        D.save_type(req.conn, req.user, req.fdict(), int(tid), req.now)
    except (Stale, NotFound) as ex:
        return types_get(req, msg=str(ex))
    except ValidationError as ex:
        return types_get(req, msg=" ".join(ex.errors.values()))
    raise Redirect("/admin/types", "Type saved.")


@route("POST", r"/admin/types/(\d+)/archive", role="admin")
def type_archive(req, tid):
    D.archive_type(req.conn, req.user, int(tid), req.f("archived") == "1", req.now)
    raise Redirect("/admin/types", "Saved.")


@route("POST", r"/admin/types/(\d+)/delete", role="admin")
def type_delete(req, tid):
    try:
        D.delete_type(req.conn, req.user, int(tid), req.now)
    except ValidationError as ex:
        return types_get(req, msg=str(ex))
    raise Redirect("/admin/types", "Type deleted.")


@route("GET", "/admin/email", role="admin")
def email_get(req, errors=None, f=None, msg=None, result=None):
    c = req.conn.execute("SELECT * FROM clinic WHERE id=1").fetchone()
    f = f or dict(c)
    over = req.app.cfg.email_overrides
    note = ""
    if over:
        note = '<div class="warnbox">These settings are fixed by the config file or environment and override this page: %s.</div>' % e(
            ", ".join(sorted(over)))
    if c["demo"]:
        note += '<div class="warnbox">This is a demo install: email is always in log mode.</div>'
    res = ""
    if result:
        res = '<div class="%s">%s</div>' % ("flash" if result[0] else "errbox", e(result[1]))
    body = note + res + ('<div class="errbox">%s</div>' % e(msg) if msg else "") + errbox(errors, ("email_mode", "smtp_host", "smtp_port", "smtp_tls", "smtp_from"))
    body += """<div class="row"><div class="card"><form method="post">%s<input type="hidden" name="version" value="%d">
    %s<p class="muted"><b>log</b> writes each email to <code>%s</code> instead of sending.</p>%s%s%s%s
    <label for="smtp_password">SMTP password</label><input type="password" id="smtp_password" name="smtp_password" autocomplete="new-password" placeholder="%s">%s
    <p><button class="primary">Save</button></p></form></div>
    <div class="card"><h2>Send test email</h2><form method="post" action="/admin/email/test">%s%s<p><button>Send test email</button></p></form></div></div>""" % (
        hidden(req), c["version"], select("email_mode", [("log", "log (outbox file)"), ("smtp", "smtp")], f.get("email_mode"), errors, "Mode"),
        e(os.path.join(req.app.cfg.data_dir, "outbox.log")), inp("smtp_host", f.get("smtp_host"), errors, "SMTP host"),
        inp("smtp_port", f.get("smtp_port"), errors, "Port", type="number"),
        select("smtp_tls", [("starttls", "STARTTLS"), ("ssl", "SSL/TLS"), ("none", "None")], f.get("smtp_tls"), errors, "TLS mode"),
        inp("smtp_user", f.get("smtp_user"), errors, "Username", autocomplete="off"),
        "leave blank to keep the saved password" if c["smtp_password"] else "", inp("smtp_from", f.get("smtp_from"), errors, "From address", type="email"),
        hidden(req), inp("to", req.f("to") or c["reply_to"], None, "Send to", type="email", required=True))
    return page(req, "Email sending", body)


@route("POST", "/admin/email", role="admin")
def email_post(req):
    f = req.fdict()
    try:
        D.update_email_settings(req.conn, req.user, f, req.now)
    except Stale as ex:
        return email_get(req, msg=str(ex))
    except ValidationError as ex:
        return email_get(req, ex.errors, f)
    raise Redirect("/admin/email", "Email settings saved.")


@route("POST", "/admin/email/test", role="admin")
def email_test(req):
    to = req.f("to").strip()
    try:
        to = D.clean_email(to, "to")
        if not to:
            raise ValidationError({"to": "Enter an address."})
    except ValidationError as ex:
        return email_get(req, result=(False, str(ex)))
    s = mailer.effective(req.conn, req.app.cfg)
    try:
        mailer.send(s, req.app.cfg.data_dir, to, "FrontDesk Book test email",
                    "This is a test email from FrontDesk Book for %s.\n" % s["clinic_name"], s["reply_to"])
        ok, text = True, ("Test email sent to %s." % to if s["email_mode"] == "smtp" else "Log mode: the test email was written to the outbox file.")
    except Exception as ex:  # noqa: BLE001
        ok, text = False, "Sending failed: %s" % (str(ex) or ex.__class__.__name__)
    with db.tx(req.conn):
        req.conn.execute("INSERT INTO email_log(at,recipient,kind,result,error,user_id) VALUES(?,?,?,?,?,?)",
                         (D.to_s(req.now), to, "test", "sent" if ok else "failed", "" if ok else text, req.user["id"]))
    return email_get(req, result=(ok, text))


@route("GET", "/admin/staff", role="admin")
def staff_get(req, errors=None, f=None, msg=None, info=None):
    rows = req.conn.execute("SELECT * FROM users ORDER BY active DESC, username").fetchall()
    trs = "".join("<tr><td>%s</td><td>%s</td><td>%s%s</td><td>%s %s %s</td></tr>" % (
        e(u["username"]), e(u["role"]), "Active" if u["active"] else "Deactivated", " (must change password)" if u["must_change"] else "",
        post_button(req, "/admin/staff/%d/reset" % u["id"], "Reset password", confirm="Reset this password?"),
        post_button(req, "/admin/staff/%d/active" % u["id"], "Deactivate" if u["active"] else "Reactivate", {"active": "0" if u["active"] else "1"}),
        post_button(req, "/admin/staff/%d/role" % u["id"], "Make %s" % ("receptionist" if u["role"] == "admin" else "admin"),
                    {"role": "receptionist" if u["role"] == "admin" else "admin"})) for u in rows)
    f = f or {}
    body = ('<div class="flash">%s</div>' % e(info) if info else "") + ('<div class="errbox">%s</div>' % e(msg) if msg else "")
    body += "<table><tr><th>Username</th><th>Role</th><th>State</th><th></th></tr>%s</table>" % trs
    body += """<div class="card"><h2>Create account</h2>%s<form method="post">%s%s%s%s%s<p class="muted">The user must change this password at first sign-in.</p>
    <button class="primary">Create</button></form></div>""" % (
        errbox(errors, ("username", "role", "password", "password2")), hidden(req), inp("username", f.get("username"), errors, "Username"),
        select("role", [("receptionist", "Receptionist"), ("admin", "Admin")], f.get("role", "receptionist"), errors, "Role"),
        inp("password", "", errors, "Initial password (at least %d characters)" % D.PASSWORD_MIN, type="password", autocomplete="new-password"),
        inp("password2", "", errors, "Initial password again", type="password", autocomplete="new-password"))
    return page(req, "Staff accounts", body)


@route("POST", "/admin/staff", role="admin")
def staff_post(req):
    f = req.fdict()
    try:
        D.create_user(req.conn, req.user, f.get("username"), f.get("role"), f.get("password"), f.get("password2"), req.now)
    except ValidationError as ex:
        return staff_get(req, ex.errors, f)
    raise Redirect("/admin/staff", "Account created.")


@route("POST", r"/admin/staff/(\d+)/reset", role="admin")
def staff_reset(req, uid):
    temp = D.reset_password(req.conn, req.user, int(uid), req.now)
    return staff_get(req, info="One-time password for %s: %s — give it to them now; it is not shown again. They must change it at sign-in." % (
        D.username_of(req.conn, int(uid)), temp))


@route("POST", r"/admin/staff/(\d+)/active", role="admin")
def staff_active(req, uid):
    try:
        D.set_user_active(req.conn, req.user, int(uid), req.f("active") == "1", req.now)
    except (ValidationError, NotFound) as ex:
        return staff_get(req, msg=str(ex))
    if int(uid) == req.user["id"] and req.f("active") != "1":
        raise Redirect("/login")
    raise Redirect("/admin/staff", "Saved.")


@route("POST", r"/admin/staff/(\d+)/role", role="admin")
def staff_role(req, uid):
    try:
        D.set_user_role(req.conn, req.user, int(uid), req.f("role"), req.now)
    except (ValidationError, NotFound) as ex:
        return staff_get(req, msg=str(ex))
    raise Redirect("/admin/staff", "Saved.")


@route("GET", "/admin/settings", role="admin")
def settings_get(req, errors=None):
    cur = D.all_settings(req.conn)
    rows = "".join("<tr><td><code>%s</code></td><td>%s</td><td>%s</td></tr>" % (
        e(k), select(k, [(v, v) for v in opts], cur[k], errors), e(desc)) for k, (opts, default, desc) in D.SETTINGS.items())
    audit = req.conn.execute("SELECT l.*, u.username FROM audit_log l LEFT JOIN users u ON u.id=l.user_id ORDER BY l.id DESC LIMIT 200").fetchall()
    atrs = "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
        e(D.fmt_dt(req.tz, a["at"])), e(a["username"] or "system"), e(a["kind"]), e(a["detail"])) for a in audit)
    body = '<form method="post">%s<table><tr><th>Setting</th><th>Value</th><th>What it decides</th></tr>%s</table><p><button class="primary">Save settings</button></p></form>' % (
        hidden(req), rows)
    body += "<h2>Audit log (latest 200)</h2><table><tr><th>When</th><th>Who</th><th>Kind</th><th>Detail</th></tr>%s</table>" % atrs
    return page(req, "Operator settings", body)


@route("POST", "/admin/settings", role="admin")
def settings_post(req):
    try:
        D.set_settings(req.conn, req.user, {k: req.f(k) for k in D.SETTINGS}, req.now)
    except ValidationError as ex:
        return settings_get(req, ex.errors)
    raise Redirect("/admin/settings", "Settings saved.")


@route("GET", "/admin/backup", role="admin")
def backup_get(req):
    body = """<div class="card"><p>Download a single file containing all data. Keep it somewhere safe (it contains patient contact details).</p>
    <p><a class="btn" href="/admin/backup/download">Download backup</a></p>
    <p class="muted">To restore: stop the service, then run <code>python3 frontdesk.py restore &lt;file&gt;</code>. See the README.</p></div>"""
    return page(req, "Backup", body)


@route("GET", "/admin/backup/download", role="admin")
def backup_download(req):
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        db.backup_to(req.conn, tmp)
        with open(tmp, "rb") as fh:
            data = fh.read()
    finally:
        os.remove(tmp)
    with db.tx(req.conn):
        D.audit(req.conn, req.user["id"], "backup", "downloaded backup", req.now)
    name = "frontdesk-backup-%s.db" % D.local(req.tz, req.now).strftime("%Y%m%d-%H%M")
    return 200, {"Content-Type": "application/octet-stream", "Content-Disposition": 'attachment; filename="%s"' % name}, data


# ------------------------------------------------------------------ dispatch
def health(app):
    """No login needed: 200 'ok' if the database opens and answers, else 503."""
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % urllib.parse.quote(app.db_path), uri=True, timeout=5)
        try:
            conn.execute("SELECT COUNT(*) FROM users").fetchone()
        finally:
            conn.close()
    except sqlite3.Error as ex:
        log.error("Health check failed: %s", ex)
        return 503, {"Content-Type": "text/plain; charset=utf-8"}, b"database unavailable\n"
    return 200, {"Content-Type": "text/plain; charset=utf-8"}, b"ok\n"


def dispatch(app, method, raw_path, headers, body):
    parsed = urllib.parse.urlsplit(raw_path)
    if parsed.path == "/health" and method == "GET":
        return health(app)
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    form = {}
    if method == "POST":
        ctype = headers.get("Content-Type", "")
        if "application/x-www-form-urlencoded" in ctype:
            form = urllib.parse.parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True)
    cookies = {}
    for part in headers.get("Cookie", "").split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            cookies[k] = v
    req = Req(app, method, parsed.path, query, form, cookies, headers)
    req.conn = db.connect(app.db_path)
    try:
        return _dispatch(req)
    finally:
        req.conn.close()


def _finish(req, resp):
    status, hdrs, body = resp
    if req.set_cookie:
        hdrs["Set-Cookie"] = req.set_cookie
    return status, hdrs, body


def _dispatch(req):
    conn = req.conn
    token = req.cookies.get("fd_session")
    if token:
        s = conn.execute("SELECT s.*, u.username, u.role, u.must_change, u.active FROM sessions s JOIN users u ON u.id=s.user_id WHERE token=?",
                         (token,)).fetchone()
        if s and s["active"] and req.now - D.from_s(s["last_seen"]) < dt.timedelta(hours=D.SESSION_IDLE_HOURS):
            req.token = token
            req.user = {"id": s["user_id"], "username": s["username"], "role": s["role"], "must_change": s["must_change"]}
            req.flash = s["flash"]
            with db.tx(conn):
                conn.execute("UPDATE sessions SET last_seen=?, flash=NULL WHERE token=?", (D.to_s(req.now), token))
        elif s:
            with db.tx(conn):
                conn.execute("DELETE FROM sessions WHERE token=?", (token,))
    if not req.token:
        # unauthenticated forms still get a CSRF token bound to a short-lived pre-session cookie
        req.token = req.cookies.get("fd_pre") or secrets.token_urlsafe(16)
        if "fd_pre" not in req.cookies:
            req.set_cookie = "fd_pre=%s; HttpOnly; SameSite=Strict; Path=/" % req.token
    try:
        for method, rx, role, fn in ROUTES:
            m = rx.match(req.path)
            if not m or method != req.method:
                continue
            if role != "public":
                if not req.user:
                    raise Redirect("/setup" if not conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] else "/login")
                if req.user["must_change"] and req.path not in ("/password", "/logout"):
                    raise Redirect("/password")
                if role == "admin" and req.user["role"] != "admin":
                    raise HTTPError(403, "Not allowed. This page is for admins only.")
            if req.method == "POST" and not hmac.compare_digest(req.f("_csrf"), req.csrf):
                raise HTTPError(400, "The form has expired. Go back, reload the page and try again.")
            return _finish(req, fn(req, *m.groups()))
        if any(rx.match(req.path) for _, rx, _, _ in ROUTES):
            raise HTTPError(405, "Method not allowed.")
        raise HTTPError(404, "Page not found.")
    except Redirect as r:
        if r.flash and req.user and req.token:
            with db.tx(conn):
                conn.execute("UPDATE sessions SET flash=? WHERE token=?", (r.flash, req.token))
        return _finish(req, (303, {"Location": r.url}, b""))
    except HTTPError as h:
        return _finish(req, page(req, {403: "Not allowed", 404: "Not found"}.get(h.code, "Error"),
                                 '<p>%s</p><p><a href="/day">Back to the day view</a></p>' % e(h.msg), h.code))
    except AppError as ex:
        return _finish(req, page(req, "Error", '<div class="errbox">%s</div><p><a href="javascript:history.back()">Go back</a></p>' % e(str(ex)), 400))
    except Exception:  # noqa: BLE001
        log.error("Unhandled error on %s %s\n%s", req.method, req.path, traceback.format_exc())
        return _finish(req, page(req, "Something went wrong", "<p>Something went wrong. The problem has been logged. "
                                                              '<a href="/day">Back to the day view</a></p>', 500))


class Handler(BaseHTTPRequestHandler):
    server_version = "FrontDeskBook"
    sys_version = ""

    def _go(self):
        raw_len = (self.headers.get("Content-Length") or "0").strip()
        if not raw_len.isdigit():
            self.send_error(400, "Invalid Content-Length")
            return
        n = int(raw_len)
        if n > 2_000_000:
            self.send_error(413)
            return
        body = self.rfile.read(n) if n else b""
        status, hdrs, out = dispatch(self.server.app, self.command, self.path, self.headers, body)
        self.send_response(status)
        hdrs.setdefault("Cache-Control", "no-store")
        hdrs["X-Frame-Options"] = "DENY"
        hdrs["X-Content-Type-Options"] = "nosniff"
        hdrs["Referrer-Policy"] = "same-origin"
        for k, v in hdrs.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    do_GET = _go
    do_POST = _go

    def log_message(self, fmt, *args):
        # request line only (no bodies, so no passwords); query strings may hold search terms, so strip them
        log.debug("%s %s", self.command, self.path.split("?")[0])
