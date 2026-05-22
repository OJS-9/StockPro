"""HTTP client error handling and pagination envelope."""

import json
import sys
import httpx
import pytest
import respx

from stockpro_cli.client import StockProClient


BASE = "http://api.test"


def _client():
    return StockProClient(BASE, "tok")


@respx.mock
def test_list_response_wrapped_in_envelope():
    respx.get(f"{BASE}/api/things").mock(
        return_value=httpx.Response(200, json=[{"id": 1}, {"id": 2}])
    )
    data = _client().get("/api/things")
    assert data == {"items": [{"id": 1}, {"id": 2}], "page": 1, "has_more": False}


@respx.mock
def test_dict_response_passes_through():
    respx.get(f"{BASE}/api/x").mock(return_value=httpx.Response(200, json={"a": 1}))
    assert _client().get("/api/x") == {"a": 1}


@respx.mock
def test_401_emits_json_error_and_exits(capsys):
    respx.get(f"{BASE}/api/x").mock(return_value=httpx.Response(401, text="bad token"))
    with pytest.raises(SystemExit) as ei:
        _client().get("/api/x")
    assert ei.value.code == 1
    err = json.loads(capsys.readouterr().err.strip())
    assert "Unauthorized" in err["error"]


@respx.mock
def test_500_emits_json_error_and_exits(capsys):
    respx.get(f"{BASE}/api/x").mock(return_value=httpx.Response(500, text="boom"))
    with pytest.raises(SystemExit):
        _client().get("/api/x")
    err = json.loads(capsys.readouterr().err.strip())
    assert "Server error" in err["error"]


@respx.mock
def test_connect_error_is_structured(capsys):
    respx.get(f"{BASE}/api/x").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(SystemExit):
        _client().get("/api/x")
    err = json.loads(capsys.readouterr().err.strip())
    assert "Cannot reach server" in err["error"]


@respx.mock
def test_timeout_is_structured(capsys):
    respx.get(f"{BASE}/api/x").mock(side_effect=httpx.TimeoutException("slow"))
    with pytest.raises(SystemExit):
        _client().get("/api/x")
    err = json.loads(capsys.readouterr().err.strip())
    assert "timed out" in err["error"]
