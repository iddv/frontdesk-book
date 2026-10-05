"""Helpers for the security probes: start the real service on 127.0.0.1 and talk raw HTTP to it."""
import os as _os
# These helpers find the repository from their own location. They live in
# tests/acceptance/_helpers/; paths are computed as if they sat one level below
# the repository root.
_HERE = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))), '_helpers', 'security_helpers.py')
import http.client
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse

REPO = os.path.dirname(os.path.dirname(os.path.abspath(_HERE)))
PW = "Correct-horse-9"


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Server:
    def __init__(self):
        self.dir = tempfile.mkdtemp(prefix="fdsec-")
        self.port = free_port()
        env = dict(os.environ, FRONTDESK_DATA_DIR=self.dir, FRONTDESK_PORT=str(self.port),
                   FRONTDESK_HOST="127.0.0.1", FRONTDESK_CONFIG=os.path.join(self.dir, "none.conf"))
        self.proc = subprocess.Popen([sys.executable, os.path.join(REPO, "frontdesk.py")], cwd=self.dir, env=env,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", self.port), 0.2).close()
                return
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("server did not start")

    def rss_kib(self):
        with open("/proc/%d/status" % self.proc.pid) as f:
            return int(re.search(r"VmRSS:\s+(\d+)", f.read()).group(1))

    def stop(self):
        self.proc.kill()
        self.proc.wait()


class Session:
    def __init__(self, srv):
        self.srv, self.cookies = srv, {}

    def req(self, method, path, form=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.port, timeout=10)
        h = dict(headers or {})
        if self.cookies:
            h["Cookie"] = "; ".join("%s=%s" % kv for kv in self.cookies.items())
        body = None
        if form is not None:
            body = urllib.parse.urlencode(form)
            h["Content-Type"] = "application/x-www-form-urlencoded"
        c.request(method, path, body, h)
        r = c.getresponse()
        data = r.read().decode("utf-8", "replace")
        for k, v in r.getheaders():
            if k.lower() == "set-cookie":
                name, val = v.split(";")[0].split("=", 1)
                if val:
                    self.cookies[name] = val
                else:
                    self.cookies.pop(name, None)
        c.close()
        return r.status, dict(r.getheaders()), data

    def csrf(self, path):
        _, _, body = self.req("GET", path)
        m = re.search(r'name="_csrf" value="([^"]+)"', body)
        return m.group(1) if m else ""

    def post(self, path, form, csrf_from=None):
        form = dict(form)
        form["_csrf"] = self.csrf(csrf_from or path)
        return self.req("POST", path, form)


def setup_admin(srv):
    s = Session(srv)
    st, h, _ = s.post("/setup", {"clinic_name": "Sec Clinic", "tz": "Europe/London", "username": "admin",
                                 "password": PW, "password2": PW})
    assert st in (200, 303), st
    return s


def raw(port, data, timeout=5):
    sock = socket.create_connection(("127.0.0.1", port), timeout)
    sock.sendall(data)
    out = b""
    try:
        while True:
            b = sock.recv(65536)
            if not b:
                break
            out += b
    except socket.timeout:
        out += b"<<TIMEOUT>>"
    sock.close()
    return out
