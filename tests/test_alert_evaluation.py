"""Unit tests for price alert evaluation against price_cache."""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from alerts.evaluation import (
    _send_email_alert_if_configured,
    _send_telegram_alert_if_connected,
    condition_met,
    evaluate_alerts_for_symbols,
)


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
    # set_price_alert_active should NOT be called -- deactivation is now
    # handled atomically inside record_price_alert_trigger
    db.set_price_alert_active.assert_not_called()


def test_evaluate_no_partial_state_on_trigger_failure(monkeypatch):
    """If record_price_alert_trigger raises, fired count stays 0."""
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
        "AAPL": {"symbol": "AAPL", "asset_type": "stock", "price": Decimal("101")}
    }
    db.record_price_alert_trigger.side_effect = RuntimeError("DB error")
    n = evaluate_alerts_for_symbols(db, ["AAPL"])
    assert n == 0
    db.set_price_alert_active.assert_not_called()


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


def test_send_telegram_alert_if_connected(monkeypatch):
    db = MagicMock()
    db.get_user_by_id.return_value = {"user_id": "u1", "telegram_chat_id": "12345"}

    sent = {"count": 0}

    def _fake_send(chat_id, text):
        sent["count"] += 1
        assert chat_id == "12345"
        assert "AAPL" in text

    monkeypatch.setattr("telegram_service.send_telegram_text_sync", _fake_send)
    _send_telegram_alert_if_connected(db, "u1", "AAPL", "AAPL is now $101")
    assert sent["count"] == 1


def test_send_email_alert_if_configured(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setenv("ALERT_FROM_SENDER", "alerts@stockpro.test")
    db = MagicMock()
    db.get_user_by_id.return_value = {"user_id": "u1", "email": "user@example.com"}

    captured = {}

    class _Resp:
        status_code = 201

    def _fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["to"] = json["to"]
        captured["text"] = json["textContent"]
        return _Resp()

    monkeypatch.setattr("requests.post", _fake_post)
    _send_email_alert_if_configured(db, "u1", "AAPL", "AAPL is now $101")
    assert captured["url"] == "https://api.brevo.com/v3/smtp/email"
    assert captured["headers"]["api-key"] == "xkeysib-test"
    assert captured["to"] == [{"email": "user@example.com"}]
    assert "AAPL" in captured["text"]


def test_send_email_alert_skips_when_unconfigured(monkeypatch):
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    monkeypatch.delenv("ALERT_FROM_SENDER", raising=False)
    db = MagicMock()

    def _boom(*args, **kwargs):
        raise AssertionError("requests.post must not be called when unconfigured")

    monkeypatch.setattr("requests.post", _boom)
    _send_email_alert_if_configured(db, "u1", "AAPL", "body")
    db.get_user_by_id.assert_not_called()


def test_send_email_alert_swallows_send_failure(monkeypatch):
    """A send exception must not propagate (error isolation)."""
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setenv("ALERT_FROM_SENDER", "alerts@stockpro.test")
    db = MagicMock()
    db.get_user_by_id.return_value = {"user_id": "u1", "email": "user@example.com"}

    def _boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr("requests.post", _boom)
    # Must not raise.
    _send_email_alert_if_configured(db, "u1", "AAPL", "body")
