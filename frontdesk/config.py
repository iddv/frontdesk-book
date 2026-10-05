"""Configuration: defaults < config file < environment variables."""
import configparser
import os

DEFAULTS = {
    "host": "127.0.0.1",
    "port": "8080",
    "data_dir": "./data",
    "log_level": "INFO",
    # Email settings left empty here are taken from the in-app Email page.
    "email_mode": "",
    "smtp_host": "",
    "smtp_port": "",
    "smtp_tls": "",
    "smtp_user": "",
    "smtp_password": "",
    "smtp_from": "",
}

EMAIL_KEYS = ("email_mode", "smtp_host", "smtp_port", "smtp_tls", "smtp_user", "smtp_password", "smtp_from")


class Config(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    @property
    def email_overrides(self):
        """Email settings fixed by the config file or environment (they win over the in-app page)."""
        return {k: self[k] for k in EMAIL_KEYS if self.get(k)}


def load(path=None):
    cfg = Config(DEFAULTS)
    path = path or os.environ.get("FRONTDESK_CONFIG") or "frontdesk.conf"
    if os.path.exists(path):
        cp = configparser.ConfigParser()
        cp.read(path, encoding="utf-8")
        if cp.has_section("frontdesk"):
            for k, v in cp.items("frontdesk"):
                if k in DEFAULTS:
                    cfg[k] = v.strip()
    for k in DEFAULTS:
        env = os.environ.get("FRONTDESK_" + k.upper())
        if env is not None and env != "":
            cfg[k] = env.strip()
    cfg["data_dir"] = os.path.abspath(cfg["data_dir"])
    try:
        cfg["port"] = int(cfg["port"])
    except ValueError:
        raise SystemExit("FRONTDESK_PORT / port must be a number, got %r" % cfg["port"])
    return cfg
