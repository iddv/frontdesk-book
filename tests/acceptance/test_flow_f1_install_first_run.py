"""Flow F1: Install and first run.

Flow: F1 in SCOPE.md.
"""

import os, re, shutil, socket, subprocess, sys, tempfile, time, urllib.request, urllib.error
from _helpers.driver import System, PW
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

def test_flow_f1_install_first_run():
    d = tempfile.mkdtemp()
    env = dict(os.environ, FRONTDESK_DATA_DIR=d, FRONTDESK_PORT=str(_port()))
    p = subprocess.Popen([sys.executable, os.path.join(REPO, "frontdesk.py")], env=env, cwd=d, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        line = ""
        for _ in range(50):
            line = p.stdout.readline()
            if "Open http" in line: break
        assert "http://127.0.0.1:%s/" % env["FRONTDESK_PORT"] in line
        r = urllib.request.urlopen("http://127.0.0.1:%s/" % env["FRONTDESK_PORT"])
        assert r.url.endswith("/setup")
    finally:
        p.terminate(); p.wait()
    # first-run screen via in-process HTTP
    s = System(setup=False)
    c = s.admin
    assert "Clinic time zone" in c.get("/setup").text
    r = c.post("/setup", {"clinic_name": "My Clinic", "tz": "Europe/London", "username": "boss", "password": PW, "password2": "different-1"}, csrf_from="/setup")
    assert "My Clinic" in r.text and "boss" in r.text  # other fields kept
    r = c.post("/setup", {"clinic_name": "My Clinic", "tz": "Europe/London", "username": "boss", "password": PW, "password2": PW}, csrf_from="/setup")
    assert "Getting started" in r.text
    assert "/setup" not in c.get("/setup").text or c.get("/setup").text.count("Sign in")
    assert s.conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0] == 0
    # demo command refuses on non-empty data
    out = subprocess.run([sys.executable, os.path.join(REPO, "frontdesk.py"), "demo"], env=dict(os.environ, FRONTDESK_DATA_DIR=s.dir), capture_output=True, text=True)
    assert "Refusing" in out.stdout + out.stderr
    s.close()
    d2 = tempfile.mkdtemp()
    out = subprocess.run([sys.executable, os.path.join(REPO, "frontdesk.py"), "demo"], env=dict(os.environ, FRONTDESK_DATA_DIR=d2), capture_output=True, text=True)
    assert "60 patients" in out.stdout and "demo-reception" in out.stdout
