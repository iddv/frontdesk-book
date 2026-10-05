"""Restore refuses while the service holds the data-dir lock.

Expected: restore exits with 'is running', nothing changed
Source: "Restore is a command that takes a backup file, refuses while the service is running"
"""

import fcntl, os, subprocess, sys, tempfile
from frontdesk import db
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_restore_refuses_while_service_holds_data_dir_lock():
    d = tempfile.mkdtemp(); db.migrate(d, log=lambda *a: None)
    fh = open(os.path.join(d, "service.lock"), "a+"); fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    bk = os.path.join(d, "b.db"); c = db.connect(db.db_path(d)); db.backup_to(c, bk); c.close()
    out = subprocess.run([sys.executable, os.path.join(REPO, "frontdesk.py"), "restore", bk], env=dict(os.environ, FRONTDESK_DATA_DIR=d), capture_output=True, text=True)
    assert "is running" in out.stdout + out.stderr and out.returncode != 0
    assert not [f for f in os.listdir(d) if f.startswith("replaced-")]
