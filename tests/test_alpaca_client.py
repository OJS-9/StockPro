"""Tests for Alpaca REST thin client (mocked HTTP)."""

import os
from unittest.mock import MagicMock, patch

import pytest

from brokerage.alpaca_client import AlpacaClient, AlpacaConfigError


def test_from_env_raises_when_missing():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(AlpacaConfigError, match="APCA_API_KEY_ID"):
            AlpacaClient.from_env()


def test_from_env_optional_returns_none_when_missing():
    with patch.dict(os.environ, {}, clear=True):
        assert AlpacaClient.from_env_optional() is None


def test_from_env_builds_client():
    with patch.dict(
        os.environ,
        {
            "APCA_API_KEY_ID": "kid",
            "APCA_API_SECRET_KEY": "sec",
            "ALPACA_BASE_URL": "https://paper-api.alpaca.markets",
        },
    ):
        c = AlpacaClient.from_env()
        assert c._base == "https://paper-api.alpaca.markets"


def test_get_account_uses_v2_account():
    with patch.dict(
        os.environ,
        {"APCA_API_KEY_ID": "k", "APCA_API_SECRET_KEY": "s"},
    ):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "ACTIVE"}
        mock_resp.raise_for_status = MagicMock()
        with patch(
            "brokerage.alpaca_client.requests.get", return_value=mock_resp
        ) as m_get:
            c = AlpacaClient.from_env()
            out = c.get_account()
        assert out["status"] == "ACTIVE"
        m_get.assert_called_once()
        url = m_get.call_args[0][0]
        assert url.endswith("/v2/account")
