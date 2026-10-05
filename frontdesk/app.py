"""Command line: run (default), demo, backup, restore, install-service, test."""
import argparse
import errno
import logging
import os
import secrets
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer

from . import config, db, domain as D, mailer, web

log = logging.getLogger("frontdesk")


class App:
    def __init__(self, cfg):
        self.cfg = cfg
        self.db_path = db.db_path(cfg.data_dir)
        self.secret = load_secret(cfg.data_dir)
        self.wake = threading.Event()
        self.stop = threading.Event()

    def reminder_loop(self):
        """Background job: runs at start (catch-up) and every minute, or sooner when woken."""
        conn = db.connect(self.db_path)
        D.recover_interrupted(conn)
        while not self.stop.is_set():
            try:
                if conn.execute("SELECT 1 FROM clinic").fetchone():
                    s = mailer.effective(conn, self.cfg)
                    n = D.process_due(conn, lambda to, subj, body, rt: mailer.send(s, self.cfg.data_dir, to, subj, body, rt))
                    if n:
                        log.info("Reminder job: %d email(s) attempted", n)
            except Exception:  # noqa: BLE001 - the job must keep running
                log.exception("Reminder job failed")
            self.wake.wait(60)
            self.wake.clear()


def load_secret(data_dir):
    path = os.path.join(data_dir, "secret.key")
    if not os.path.exists(path):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return f.read().strip().encode()


_lock_handle = None


def acquire_lock(data_dir):
    """Holds an exclusive lock on data/service.lock while the service runs. Returns False if already held."""
    global _lock_handle
    path = os.path.join(data_dir, "service.lock")
    fh = open(path, "a+")
    try:
        if os.name == "nt":
            import msvcrt
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return False
    _lock_handle = fh
    return True


def prepare(cfg):
    os.makedirs(cfg.data_dir, exist_ok=True)
    db.migrate(cfg.data_dir, log=log.info)


def cmd_run(cfg, demo=False):
    prepare(cfg)
    if not acquire_lock(cfg.data_dir):
        sys.exit("FrontDesk Book is already running with data directory %s." % cfg.data_dir)
    if demo:
        from . import demo as demo_mod
        conn = db.connect(db.db_path(cfg.data_dir))
        try:
            demo_mod.load(conn)
        except SystemExit as ex:
            print(ex)
            sys.exit(1)
        finally:
            conn.close()
    app = App(cfg)
    try:
        server = ThreadingHTTPServer((cfg.host, cfg.port), web.Handler)
    except OSError as ex:
        if ex.errno in (errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", -1)):
            sys.exit("Port %d on %s is already in use. Set FRONTDESK_PORT (or port= in frontdesk.conf) to choose another port."
                     % (cfg.port, cfg.host))
        sys.exit("Cannot listen on %s:%d: %s. Check FRONTDESK_HOST / FRONTDESK_PORT." % (cfg.host, cfg.port, ex.strerror))
    server.daemon_threads = True
    server.app = app
    threading.Thread(target=app.reminder_loop, name="reminders", daemon=True).start()
    host = "127.0.0.1" if cfg.host in ("0.0.0.0", "") else cfg.host
    print("FrontDesk Book is running. Open http://%s:%d/ in your browser. (Ctrl+C to stop)" % (host, cfg.port), flush=True)
    log.info("Data directory: %s", cfg.data_dir)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping.")
    finally:
        app.stop.set()
        app.wake.set()
        server.server_close()


def cmd_demo(cfg):
    prepare(cfg)
    if not acquire_lock(cfg.data_dir):
        sys.exit("Stop the running service before loading demo data.")
    from . import demo as demo_mod
    conn = db.connect(db.db_path(cfg.data_dir))
    try:
        demo_mod.load(conn)
    except SystemExit as ex:
        print(ex)
        sys.exit(1)
    finally:
        conn.close()


def cmd_backup(cfg, dest):
    prepare(cfg)
    conn = db.connect(db.db_path(cfg.data_dir))
    dest = dest or os.path.join(cfg.data_dir, "backups", "frontdesk-backup-%s.db" % db.stamp())
    db.backup_to(conn, dest)
    conn.close()
    print("Backup written to %s" % dest)


def cmd_restore(cfg, src):
    if not os.path.exists(src):
        sys.exit("No such file: %s" % src)
    os.makedirs(cfg.data_dir, exist_ok=True)
    if not acquire_lock(cfg.data_dir):
        sys.exit("FrontDesk Book is running. Stop the service first, then run restore again. Nothing was changed.")
    db.restore(cfg.data_dir, src, log=print)
    db.migrate(cfg.data_dir, log=print)
    print("Done. Start the service again.")


def cmd_install_service(cfg):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    py = sys.executable
    if sys.platform.startswith("linux"):
        unit_dir = os.path.expanduser("~/.config/systemd/user")
        os.makedirs(unit_dir, exist_ok=True)
        unit = os.path.join(unit_dir, "frontdesk-book.service")
        conf = os.path.abspath("frontdesk.conf")
        with open(unit, "w") as f:
            f.write("[Unit]\nDescription=FrontDesk Book\nAfter=network.target\n\n[Service]\nWorkingDirectory=%s\n"
                    "Environment=FRONTDESK_DATA_DIR=%s\nEnvironment=FRONTDESK_CONFIG=%s\nExecStart=%s %s run\nRestart=on-failure\n\n"
                    "[Install]\nWantedBy=default.target\n" % (here, cfg.data_dir, conf, py, os.path.join(here, "frontdesk.py")))
        print("Wrote %s" % unit)
        for c in (["systemctl", "--user", "daemon-reload"], ["systemctl", "--user", "enable", "--now", "frontdesk-book.service"],
                  ["loginctl", "enable-linger", os.environ.get("USER", "")]):
            r = subprocess.run(c, capture_output=True, text=True)
            print("$ %s -> %s" % (" ".join(c), "ok" if r.returncode == 0 else r.stderr.strip()))
        print("The service now starts with the computer. Status: systemctl --user status frontdesk-book")
    elif sys.platform == "darwin":
        plist = os.path.expanduser("~/Library/LaunchAgents/com.frontdesk.book.plist")
        os.makedirs(os.path.dirname(plist), exist_ok=True)
        with open(plist, "w") as f:
            f.write('<?xml version="1.0" encoding="UTF-8"?>\n<plist version="1.0"><dict><key>Label</key><string>com.frontdesk.book</string>'
                    '<key>ProgramArguments</key><array><string>%s</string><string>%s</string><string>run</string></array>'
                    '<key>WorkingDirectory</key><string>%s</string><key>EnvironmentVariables</key><dict><key>FRONTDESK_DATA_DIR</key>'
                    '<string>%s</string></dict><key>RunAtLoad</key><true/><key>KeepAlive</key><true/></dict></plist>\n'
                    % (py, os.path.join(here, "frontdesk.py"), here, cfg.data_dir))
        subprocess.run(["launchctl", "load", "-w", plist])
        print("Installed %s; FrontDesk Book now starts at login." % plist)
    elif os.name == "nt":
        cmd = 'schtasks /Create /F /SC ONLOGON /TN FrontDeskBook /TR "\\"%s\\" \\"%s\\" run"' % (py, os.path.join(here, "frontdesk.py"))
        r = subprocess.run(cmd, shell=True)
        print("Scheduled task FrontDeskBook created." if r.returncode == 0 else "Could not create the scheduled task.")
    else:
        print("Unsupported platform for automatic service install; run `python3 frontdesk.py run` at startup.")


def cmd_test():
    import unittest
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    suite = unittest.defaultTestLoader.discover(os.path.join(here, "tests"), top_level_dir=here)
    res = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if res.wasSuccessful() else 1)


def main(argv=None):
    p = argparse.ArgumentParser(prog="frontdesk.py", description="FrontDesk Book appointment book")
    p.add_argument("--config", help="config file (default ./frontdesk.conf)")
    p.add_argument("--demo", action="store_true", help="load demo data into an empty install, then run")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("run", help="start the service (default)")
    sub.add_parser("demo", help="load demo data into an empty install and exit")
    b = sub.add_parser("backup", help="write a backup file")
    b.add_argument("dest", nargs="?")
    r = sub.add_parser("restore", help="restore a backup file (service must be stopped)")
    r.add_argument("file")
    sub.add_parser("install-service", help="start FrontDesk Book automatically with the computer")
    sub.add_parser("test", help="run the automated tests")
    a = p.parse_args(argv)
    if a.cmd == "test":
        return cmd_test()
    cfg = config.load(a.config)
    logging.basicConfig(level=getattr(logging, str(cfg.log_level).upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if a.cmd == "demo":
        cmd_demo(cfg)
    elif a.cmd == "backup":
        cmd_backup(cfg, a.dest)
    elif a.cmd == "restore":
        cmd_restore(cfg, a.file)
    elif a.cmd == "install-service":
        cmd_install_service(cfg)
    else:
        cmd_run(cfg, demo=a.demo)
