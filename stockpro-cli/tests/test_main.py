"""Top-level CLI behavior: missing auth, version, destructive commands."""

import json
import pytest
from stockpro_cli.main import cli


def test_missing_auth_returns_structured_error(runner, tmp_config_home, mock_keyring):
    result = runner.invoke(cli, ["usage"])
    assert result.exit_code == 1
    payload = json.loads(result.stderr.strip())
    assert "Not authenticated" in payload["error"]


def test_delete_account_requires_yes_in_machine_mode(authed_runner):
    # CliRunner has no TTY -- machine mode applies. Without --yes-i-mean-it: exit 2.
    result = authed_runner.invoke(cli, ["delete-account", "--confirm"])
    assert result.exit_code == 2
    payload = json.loads(result.stderr.strip())
    assert "yes-i-mean-it" in payload["error"]


def test_help_works(runner):
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "StockPro CLI" in result.output
