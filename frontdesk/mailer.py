"""Email sending: SMTP, or 'log' mode that appends to an outbox file in the data directory."""
import os
import smtplib
import ssl
import threading
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

_outbox_lock = threading.Lock()


def effective(conn, cfg):
    """Email settings from the Email page, overridden by config file/env values; demo data always uses log mode."""
    c = conn.execute("SELECT * FROM clinic WHERE id=1").fetchone()
    s = {k: (c[k] if c else "") for k in ("email_mode", "smtp_host", "smtp_port", "smtp_tls", "smtp_user", "smtp_password", "smtp_from")}
    s["email_mode"] = s["email_mode"] or "log"
    s.update(cfg.email_overrides)
    s["reply_to"] = c["reply_to"] if c else ""
    s["clinic_name"] = c["name"] if c else "Clinic"
    if c and c["demo"]:
        s["email_mode"] = "log"
    return s


def is_configured(s):
    return s["email_mode"] == "smtp" and bool(s["smtp_host"])


def send(s, data_dir, to, subject, body, reply_to=""):
    msg = EmailMessage()
    sender = s.get("smtp_from") or "frontdesk@localhost"
    msg["From"] = "%s <%s>" % (s.get("clinic_name", "Clinic").replace("<", "").replace(">", ""), sender)
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1])
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)
    if s["email_mode"] != "smtp":
        with _outbox_lock, open(os.path.join(data_dir, "outbox.log"), "a", encoding="utf-8") as f:
            f.write("=" * 72 + "\n" + msg.as_string() + "\n")
        return
    port = int(s.get("smtp_port") or 587)
    tls = s.get("smtp_tls") or "starttls"
    ctx = ssl.create_default_context()
    if tls == "ssl":
        server = smtplib.SMTP_SSL(s["smtp_host"], port, timeout=30, context=ctx)
    else:
        server = smtplib.SMTP(s["smtp_host"], port, timeout=30)
    try:
        if tls == "starttls":
            server.starttls(context=ctx)
        if s.get("smtp_user"):
            server.login(s["smtp_user"], s.get("smtp_password") or "")
        server.send_message(msg)
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001
            pass
