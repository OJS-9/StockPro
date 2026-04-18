"""Read/write ~/.stockpro/config.json for token + API URL storage."""

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
        return json.loads(CONFIG_FILE.read_text())
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
    return os.environ.get("STOCKPRO_TOKEN") or load_config().get("access_token")


def clear_auth():
    cfg = load_config()
    cfg.pop("access_token", None)
    save_config(cfg)
