"""Unit tests for price alert evaluation against price_cache."""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from alerts.evaluation import condition_met, evaluate_alerts_for_symbols


def test_condition_met_above_below():
    assert condition_met("above", 10.0, 10.0) is True
    assert condition_met("above", 10.01, 10.0) is True
    assert condition_met("above", 9.99, 10.0) is False
    assert condition_met("below", 10.0, 10.0) is True
    assert condition_met("below", 9.99, 10.0) is True
    assert condition_met("below", 10.01, 10.0) is False


def test_evaluate_fires_when_met(monkeypatch):
    monkeypatch.setenv("STOCKPRO_ALERT_COOLDOWN_SEC", "0")
    db = MagicMock()
    db.list_active_alerts_for_symbols.return_value = [
        {
            "alert_id": "a1",
            "user_id": "u1",
            "symbol": "AAPL",
            "asset_type": "stock",
            "direction": "above",
            "target_price": Decimal("100"),
            "last_triggered_at": None,
        }
    ]
    db.get_cached_prices.return_value = {
        "AAPL": {
            "symbol": "AAPL",
            "asset_type": "stock",
            "price": Decimal("101"),
        }
    }
    n = evaluate_alerts_for_symbols(db, ["aapl"])
    assert n == 1
    db.record_price_alert_trigger.assert_called_once()
    call = db.record_price_alert_trigger.call_args[0]
    assert call[1] == "u1"
    assert call[2] == "a1"
    assert "AAPL" in call[4] and "$" in call[4]


def test_evaluate_respects_cooldown(monkeypatch):
    monkeypatch.setenv("STOCKPRO_ALERT_COOLDOWN_SEC", "3600")
    db = MagicMock()
    db.list_active_alerts_for_symbols.return_value = [
        {
            "alert_id": "a1",
            "user_id": "u1",
            "symbol": "AAPL",
            "asset_type": "stock",
            "direction": "above",
            "target_price": Decimal("100"),
            "last_triggered_at": datetime.utcnow() - timedelta(minutes=5),
        }
    ]
    db.get_cached_prices.return_value = {
        "AAPL": {"symbol": "AAPL", "asset_type": "stock", "price": 150.0}
    }
    n = evaluate_alerts_for_symbols(db, ["AAPL"])
    assert n == 0
    db.record_price_alert_trigger.assert_not_called()


def test_evaluate_skips_asset_type_mismatch(monkeypatch):
    monkeypatch.setenv("STOCKPRO_ALERT_COOLDOWN_SEC", "0")
    db = MagicMock()
    db.list_active_alerts_for_symbols.return_value = [
        {
            "alert_id": "a1",
            "user_id": "u1",
            "symbol": "BTC",
            "asset_type": "stock",
            "direction": "above",
            "target_price": 1,
            "last_triggered_at": None,
        }
    ]
    db.get_cached_prices.return_value = {
        "BTC": {"symbol": "BTC", "asset_type": "crypto", "price": 50000}
    }
    n = evaluate_alerts_for_symbols(db, ["BTC"])
    assert n == 0
    db.record_price_alert_trigger.assert_not_called()
