"""Unit tests for WebSocket price snapshot helpers (no live WebSocket)."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from realtime.ws_prices import (
    fetch_prices_snapshot,
    normalize_symbols,
    parse_symbols_message,
)


def test_normalize_symbols_dedupes_and_caps():
    assert normalize_symbols(["aapl", "AAPL", " msft ", "x" * 100], max_n=2) == [
        "AAPL",
        "MSFT",
    ]


def test_parse_symbols_message_valid():
    raw = json.dumps({"symbols": ["aapl", "MSFT"]})
    assert parse_symbols_message(raw) == ["AAPL", "MSFT"]


def test_parse_symbols_message_invalid():
    assert parse_symbols_message("not json") is None
    assert parse_symbols_message("{}") is None
    assert parse_symbols_message("[]") is None


def test_fetch_prices_snapshot_maps_rows():
    fake_row = {
        "symbol": "AAPL",
        "asset_type": "stock",
        "price": 100.5,
        "change_percent": 1.25,
        "display_name": "Apple",
        "last_updated": datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    }
    mock_db = MagicMock()
    mock_db.get_cached_prices.return_value = {"AAPL": fake_row}

    with patch("database.get_database_manager", return_value=mock_db):
        out = fetch_prices_snapshot(["AAPL", "ZZZ"])

    assert "AAPL" in out and "ZZZ" in out
    assert out["AAPL"]["price"] == 100.5
    assert out["AAPL"]["last_updated"] is not None
    assert out["ZZZ"] is None
