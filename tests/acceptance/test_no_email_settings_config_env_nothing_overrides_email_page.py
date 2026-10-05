"""With no email settings in config/env, nothing overrides the Email page.

Expected: email_overrides is empty
Source: "Any email setting in the config file or environment overrides the page (README)"
"""

import os, tempfile
from frontdesk import config

def test_no_email_settings_config_env_nothing_overrides_email_page(monkeypatch=None):
    saved = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("FRONTDESK_SMTP") or k == "FRONTDESK_EMAIL_MODE"}
    try:
        cfg = config.load(os.path.join(tempfile.mkdtemp(), "none.conf"))
        assert cfg.email_overrides == {}
    finally:
        os.environ.update(saved)
