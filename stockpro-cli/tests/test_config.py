"""Config file storage and API URL resolution."""

from stockpro_cli import config as cfg_mod


def test_default_api_url(tmp_config_home, mock_keyring):
    assert cfg_mod.get_api_url() == cfg_mod.DEFAULT_API_URL


def test_env_var_overrides_api_url(tmp_config_home, mock_keyring, monkeypatch):
    monkeypatch.setenv("STOCKPRO_API_URL", "http://override.test")
    assert cfg_mod.get_api_url() == "http://override.test"


def test_config_file_used_when_no_env(tmp_config_home, mock_keyring):
    cfg_mod.save_config({"api_url": "http://from-file.test"})
    assert cfg_mod.get_api_url() == "http://from-file.test"


def test_corrupt_config_returns_empty(tmp_config_home, mock_keyring):
    cfg_mod._ensure_dir()
    cfg_mod.CONFIG_FILE.write_text("not json")
    assert cfg_mod.load_config() == {}
