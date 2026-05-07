"""Keychain storage + legacy file migration."""

import json


def test_store_and_load(tmp_config_home, mock_keyring):
    from stockpro_cli.keychain import store_token, load_token
    store_token("hello")
    assert load_token() == "hello"


def test_clear(tmp_config_home, mock_keyring):
    from stockpro_cli.keychain import store_token, load_token, clear_token
    store_token("hello")
    clear_token()
    assert load_token() is None


def test_env_var_overrides(tmp_config_home, mock_keyring, monkeypatch):
    from stockpro_cli.keychain import store_token, load_token
    store_token("from-keychain")
    monkeypatch.setenv("STOCKPRO_TOKEN", "from-env")
    assert load_token() == "from-env"


def test_legacy_file_token_migrates(tmp_config_home, mock_keyring):
    from stockpro_cli import config as cfg_mod
    from stockpro_cli.keychain import load_token
    cfg_mod.save_config({"access_token": "legacy-tok"})
    # First read should migrate.
    assert load_token() == "legacy-tok"
    # File should no longer carry the token.
    on_disk = json.loads(cfg_mod.CONFIG_FILE.read_text())
    assert "access_token" not in on_disk
    # Subsequent reads come from keychain.
    assert load_token() == "legacy-tok"


def test_load_returns_none_when_empty(tmp_config_home, mock_keyring):
    from stockpro_cli.keychain import load_token
    assert load_token() is None
