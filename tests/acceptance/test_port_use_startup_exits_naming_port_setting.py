"""Port in use: startup exits naming the port and the setting.

Expected: message 'Port N ... already in use ... FRONTDESK_PORT'
Source: "Port in use: startup exits with a message naming the port and the setting that changes it."
"""

import os, socket, subprocess, sys, tempfile
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_port_use_startup_exits_naming_port_setting():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen(); port = s.getsockname()[1]
    try:
        out = subprocess.run([sys.executable, os.path.join(REPO, "frontdesk.py")], env=dict(os.environ, FRONTDESK_DATA_DIR=tempfile.mkdtemp(), FRONTDESK_PORT=str(port)),
                             capture_output=True, text=True, timeout=20)
        msg = out.stdout + out.stderr
        assert "Port %d" % port in msg and "already in use" in msg and "FRONTDESK_PORT" in msg
    finally:
        s.close()
