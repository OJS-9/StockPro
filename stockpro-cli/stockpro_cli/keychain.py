"""Token storage in the OS keychain with file-based fallback for legacy installs and headless CI.

Resolution order on read:
  1. STOCKPRO_TOKEN env var (highest precedence -- required for CI/headless).
  2. OS keychain via the `keyring` library.
  3. Legacy ~/.stockpro/config.json `access_token`. If found, migrate into the
     keychain and remove from the config file.
"""

import os
import sys
from typing import Optional

_SERVICE = "stockpro"
_USERNAME = "access_token"


def _config_module():
    # Imported lazily to avoid circular import (config.py imports nothing from here).
    from stockpro_cli import config
    return config


def _get_keyring():
    """Return the `keyring` module if available and a backend is usable, else None."""
    try:
        import keyring
        from keyring.errors import NoKeyringError
    except Exception:
        return None
    try:
        # Touch the backend to detect NoKeyringError early.
        keyring.get_keyring()
    except NoKeyringError:
        return None
    except Exception:
        return None
    return keyring


def store_token(token: str) -> None:
    """Persist a token. Prefer keychain; fall back to config file with a warning."""
    kr = _get_keyring()
    if kr is None:
        sys.stderr.write(
            "warning: OS keychain unavailable; storing token in ~/.stockpro/config.json\n"
        )
        cfg_mod = _config_module()
        cfg = cfg_mod.load_config()
        cfg["access_token"] = token
        cfg_mod.save_config(cfg)
        return
    try:
        kr.set_password(_SERVICE, _USERNAME, token)
        # Wipe any legacy file token so we never have two sources of truth.
        cfg_mod = _config_module()
        cfg = cfg_mod.load_config()
        if "access_token" in cfg:
            cfg.pop("access_token", None)
            cfg_mod.save_config(cfg)
    except Exception as exc:
        sys.stderr.write(f"warning: keychain write failed ({exc}); falling back to file\n")
        cfg_mod = _config_module()
        cfg = cfg_mod.load_config()
        cfg["access_token"] = token
        cfg_mod.save_config(cfg)


def load_token() -> Optional[str]:
    """Return the stored token. Migrates legacy file tokens into the keychain on first read."""
    env = os.environ.get("STOCKPRO_TOKEN")
    if env:
        return env

    kr = _get_keyring()
    if kr is not None:
        try:
            tok = kr.get_password(_SERVICE, _USERNAME)
        except Exception:
            tok = None
        if tok:
            return tok

    cfg_mod = _config_module()
    cfg = cfg_mod.load_config()
    legacy = cfg.get("access_token")
    if not legacy:
        return None

    # Migrate.
    if kr is not None:
        try:
            kr.set_password(_SERVICE, _USERNAME, legacy)
            cfg.pop("access_token", None)
            cfg_mod.save_config(cfg)
        except Exception:
            pass
    return legacy


def clear_token() -> None:
    """Remove the token from both keychain and legacy config file."""
    kr = _get_keyring()
    if kr is not None:
        try:
            kr.delete_password(_SERVICE, _USERNAME)
        except Exception:
            pass
    cfg_mod = _config_module()
    cfg = cfg_mod.load_config()
    if "access_token" in cfg:
        cfg.pop("access_token", None)
        cfg_mod.save_config(cfg)
