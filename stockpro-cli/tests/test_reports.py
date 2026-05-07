"""reports command: trade-type aliases, delete-all guards."""

import json
from stockpro_cli.main import cli
from stockpro_cli.commands.reports import _normalize_trade_type


def test_trade_type_alias_swing():
    assert _normalize_trade_type(None, None, "swing") == "Swing Trade"


def test_trade_type_alias_day():
    assert _normalize_trade_type(None, None, "DAY") == "Day Trade"


def test_trade_type_canonical_with_space():
    assert _normalize_trade_type(None, None, "swing trade") == "Swing Trade"


def test_trade_type_invalid():
    import click
    import pytest
    with pytest.raises(click.BadParameter):
        _normalize_trade_type(None, None, "scalping")


def test_delete_all_machine_mode_requires_yes(authed_runner):
    result = authed_runner.invoke(cli, ["reports", "delete-all", "--confirm"])
    assert result.exit_code == 2
    err = result.stderr if result.stderr else result.output
    payload = json.loads(err.strip().splitlines()[-1])
    assert "yes-i-mean-it" in payload["error"]
