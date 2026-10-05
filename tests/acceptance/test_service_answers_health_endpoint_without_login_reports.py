"""The service answers a health endpoint without a login and reports whether the database can be opened.

Expected: GET /health (or /healthz) returns 200 without a session, with a body saying the database is ok
Source: the readiness checks (READINESS.md).
"""

import os, socket, subprocess, sys, tempfile, time, urllib.error, urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def test_health_endpoint_without_login():
    port = _free_port()
    data = tempfile.mkdtemp()
    env = dict(os.environ, FRONTDESK_HOST="127.0.0.1", FRONTDESK_PORT=str(port), FRONTDESK_DATA_DIR=data)
    proc = subprocess.Popen([sys.executable, str(REPO / "frontdesk.py")], cwd=data, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", port), 0.2).close(); break
            except OSError:
                time.sleep(0.1)
        results = {}
        for path in ("/health", "/healthz"):
            try:
                r = urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=5)
                results[path] = (r.status, r.read().decode("utf-8", "replace").lower())
            except urllib.error.HTTPError as e:
                results[path] = (e.code, "")
        ok = [p for p, (code, body) in results.items() if code == 200 and ("ok" in body or "database" in body)]
        assert ok, "no unauthenticated health endpoint reporting database state: %r" % {k: v[0] for k, v in results.items()}
    finally:
        proc.terminate(); proc.wait(10)
