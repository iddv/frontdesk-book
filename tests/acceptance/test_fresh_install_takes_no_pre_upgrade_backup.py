"""A fresh install takes no pre-upgrade backup.

Expected: no pre-upgrade-* file in data/backups
Source: "Upgrades apply migrations automatically at start after taking an automatic backup."
"""

import os, tempfile
from frontdesk import db

def test_fresh_install_takes_no_pre_upgrade_backup():
    d = tempfile.mkdtemp(); open(db.db_path(d), "wb").close()  # empty store, schema version 0
    db.migrate(d, log=lambda *a: None)
    b = os.path.join(d, "backups")
    assert not (os.path.isdir(b) and [f for f in os.listdir(b) if f.startswith("pre-upgrade")])
