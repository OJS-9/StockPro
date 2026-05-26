"""portfolio cash subcommands: routes, payloads, client-side validation."""

import json
import httpx
import respx

from stockpro_cli.main import cli


BASE = "http://api.test"
PID = "abc123"


def _invoke(authed_runner, args):
    return authed_runner.invoke(cli, ["--api-url", BASE, *args])


@respx.mock
def test_cash_show_extracts_cash_fields(authed_runner):
    respx.get(f"{BASE}/api/portfolio/{PID}").mock(
        return_value=httpx.Response(
            200,
            json={
                "portfolio_id": PID,
                "holdings": [],
                "cash_balance": 1500.0,
                "track_cash": True,
                "name": "Main",
            },
        )
    )
    result = _invoke(authed_runner, ["portfolio", "cash", "show", "--id", PID])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload == {"portfolio_id": PID, "cash_balance": 1500.0, "track_cash": True}


@respx.mock
def test_cash_set_posts_action_set(authed_runner):
    route = respx.post(f"{BASE}/api/portfolio/{PID}/cash").mock(
        return_value=httpx.Response(200, json={"ok": True, "cash_balance": 5000.0})
    )
    result = _invoke(authed_runner, ["portfolio", "cash", "set", "--id", PID, "--amount", "5000"])
    assert result.exit_code == 0, result.output
    sent = json.loads(route.calls.last.request.content)
    assert sent == {"action": "set", "amount": 5000.0}


@respx.mock
def test_cash_deposit_posts_action_deposit(authed_runner):
    route = respx.post(f"{BASE}/api/portfolio/{PID}/cash").mock(
        return_value=httpx.Response(200, json={"ok": True, "cash_balance": 6000.0})
    )
    result = _invoke(authed_runner, ["portfolio", "cash", "deposit", "--id", PID, "--amount", "1000"])
    assert result.exit_code == 0, result.output
    sent = json.loads(route.calls.last.request.content)
    assert sent == {"action": "deposit", "amount": 1000.0}


@respx.mock
def test_cash_withdraw_posts_action_withdraw(authed_runner):
    route = respx.post(f"{BASE}/api/portfolio/{PID}/cash").mock(
        return_value=httpx.Response(200, json={"ok": True, "cash_balance": 4750.0})
    )
    result = _invoke(authed_runner, ["portfolio", "cash", "withdraw", "--id", PID, "--amount", "250"])
    assert result.exit_code == 0, result.output
    sent = json.loads(route.calls.last.request.content)
    assert sent == {"action": "withdraw", "amount": 250.0}


@respx.mock
def test_cash_enable_hits_toggle_route(authed_runner):
    route = respx.post(f"{BASE}/api/portfolio/{PID}/toggle-cash").mock(
        return_value=httpx.Response(200, json={"ok": True, "track_cash": True})
    )
    result = _invoke(authed_runner, ["portfolio", "cash", "enable", "--id", PID])
    assert result.exit_code == 0, result.output
    assert route.called


def test_cash_deposit_rejects_zero_amount(authed_runner):
    result = _invoke(authed_runner, ["portfolio", "cash", "deposit", "--id", PID, "--amount", "0"])
    assert result.exit_code != 0


def test_cash_set_rejects_negative_amount(authed_runner):
    result = _invoke(authed_runner, ["portfolio", "cash", "set", "--id", PID, "--amount", "-5"])
    assert result.exit_code != 0
