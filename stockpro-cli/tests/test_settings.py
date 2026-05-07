"""settings update --json-data error handling."""

import json
from stockpro_cli.main import cli


def test_settings_update_bad_json_exits_2(authed_runner):
    result = authed_runner.invoke(cli, ["settings", "update", "--json-data", "not json"])
    assert result.exit_code == 2
    err = result.stderr if result.stderr else result.output
    payload = json.loads(err.strip().splitlines()[-1])
    assert "Invalid --json-data" in payload["error"]


def test_settings_update_non_object_json_exits_2(authed_runner):
    result = authed_runner.invoke(cli, ["settings", "update", "--json-data", "42"])
    assert result.exit_code == 2
    err = result.stderr if result.stderr else result.output
    payload = json.loads(err.strip().splitlines()[-1])
    assert "must be a JSON object" in payload["error"]
