"""Read/write ~/.stockpro/config.json for non-secret config (API URL).

Tokens live in the OS keychain — see `keychain.py`. Legacy file-stored tokens are
migrated on first read.
"""

import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".stockpro"
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_API_URL = "https://stockpro-production-11c8.up.railway.app"


def _ensure_dir():
    CONFIG_DIR.mkdir(mode=0o700, exist_ok=True)


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_config(data: dict):
    _ensure_dir()
    CONFIG_FILE.write_text(json.dumps(data, indent=2))
    CONFIG_FILE.chmod(0o600)


def get_api_url() -> str:
    return (
        os.environ.get("STOCKPRO_API_URL")
        or load_config().get("api_url")
        or DEFAULT_API_URL
    )


def get_token() -> str | None:
    from stockpro_cli.keychain import load_token
    return load_token()


def clear_auth():
    from stockpro_cli.keychain import clear_token
    clear_token()
