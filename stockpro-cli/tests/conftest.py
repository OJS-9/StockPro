"""Shared fixtures for the StockPro CLI test suite."""

import pytest
from click.testing import CliRunner


class _InMemoryKeyring:
    """Minimal in-memory `keyring` backend for tests."""

    priority = 1

    def __init__(self):
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self._store.get((service, username))

    def set_password(self, service, username, password):
        self._store[(service, username)] = password

    def delete_password(self, service, username):
        self._store.pop((service, username), None)


@pytest.fixture
def runner():
    try:
        return CliRunner(mix_stderr=False)
    except TypeError:
        # Click 8.2+ removed mix_stderr; stderr is already separate.
        return CliRunner()


@pytest.fixture
def tmp_config_home(monkeypatch, tmp_path):
    """Redirect ~/.stockpro to a tmp dir so tests don't touch the real config."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    # config.py captured CONFIG_DIR / CONFIG_FILE at import time -- patch them too.
    from stockpro_cli import config as cfg_mod
    monkeypatch.setattr(cfg_mod, "CONFIG_DIR", home / ".stockpro")
    monkeypatch.setattr(cfg_mod, "CONFIG_FILE", home / ".stockpro" / "config.json")
    monkeypatch.delenv("STOCKPRO_TOKEN", raising=False)
    monkeypatch.delenv("STOCKPRO_API_URL", raising=False)
    yield home


@pytest.fixture
def mock_keyring(monkeypatch):
    """Replace the system keyring backend with an in-memory one."""
    import keyring
    backend = _InMemoryKeyring()
    monkeypatch.setattr(keyring, "get_keyring", lambda: backend)
    monkeypatch.setattr(keyring, "get_password", backend.get_password)
    monkeypatch.setattr(keyring, "set_password", backend.set_password)
    monkeypatch.setattr(keyring, "delete_password", backend.delete_password)
    return backend


@pytest.fixture
def authed_runner(runner, tmp_config_home, mock_keyring):
    """A CliRunner with a fake token already in the keychain."""
    from stockpro_cli.keychain import store_token
    store_token("test-token-abc")
    return runner
