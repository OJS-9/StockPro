"""Unit tests for the weekly portfolio digest email (issue #129)."""

import importlib.util
import os
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from email_service import send_weekly_digest_email


class _Resp:
    def __init__(self, status_code=201):
        self.status_code = status_code


def _capture_post(captured, status_code=201):
    def _fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["to"] = json["to"]
        captured["subject"] = json["subject"]
        captured["text"] = json["textContent"]
        captured["html"] = json["htmlContent"]
        return _Resp(status_code)

    return _fake_post


# --------------------------------------------------------------------------- #
# Email copy + rendering
# --------------------------------------------------------------------------- #

def _full_data():
    return {
        "total_value": Decimal("12345.67"),
        "week_change_pct": Decimal("2.3"),
        "top_mover": {"symbol": "AAPL", "pct": Decimal("5.1")},
        "holdings_count": 3,
    }


def test_digest_en_up_week(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setenv("ALERT_FROM_SENDER", "alerts@stockpro.test")
    monkeypatch.setenv("APP_BASE_URL", "https://stock-pro.org")
    captured = {}
    monkeypatch.setattr("requests.post", _capture_post(captured))

    ok = send_weekly_digest_email("user@example.com", "Sam", _full_data(), "en")

    assert ok is True
    assert captured["to"] == [{"email": "user@example.com"}]
    assert "up 2.3%" in captured["subject"]
    assert "Sam" in captured["html"]
    assert "$12,345.67" in captured["html"]
    assert "+2.3%" in captured["html"]
    assert "AAPL +5.1%" in captured["html"]
    # Positive change uses the green accent token.
    assert "#22c55e" in captured["html"]
    assert "https://stock-pro.org/portfolio" in captured["html"]
    assert "https://stock-pro.org/portfolio" in captured["text"]


def test_digest_en_down_week_uses_red(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setenv("ALERT_FROM_SENDER", "alerts@stockpro.test")
    captured = {}
    monkeypatch.setattr("requests.post", _capture_post(captured))

    data = _full_data()
    data["week_change_pct"] = Decimal("-1.2")
    data["top_mover"] = {"symbol": "TSLA", "pct": Decimal("-4.0")}
    ok = send_weekly_digest_email("user@example.com", "Sam", data, "en")

    assert ok is True
    assert "down 1.2%" in captured["subject"]
    assert "-1.2%" in captured["html"]
    assert "#ef4444" in captured["html"]


def test_digest_he_is_rtl(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setenv("ALERT_FROM_SENDER", "alerts@stockpro.test")
    captured = {}
    monkeypatch.setattr("requests.post", _capture_post(captured))

    ok = send_weekly_digest_email("user@example.com", "Dana", _full_data(), "he")

    assert ok is True
    assert 'dir="rtl"' in captured["html"]
    assert "היי" in captured["html"]  # Hebrew greeting
    assert "השבוע" in captured["subject"]


def test_digest_without_baseline_omits_change(monkeypatch):
    """A user with no week-ago baseline still gets a value-only digest."""
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setenv("ALERT_FROM_SENDER", "alerts@stockpro.test")
    captured = {}
    monkeypatch.setattr("requests.post", _capture_post(captured))

    data = {
        "total_value": Decimal("500.00"),
        "week_change_pct": None,
        "top_mover": None,
        "holdings_count": 1,
    }
    ok = send_weekly_digest_email("user@example.com", "Sam", data, "en")

    assert ok is True
    assert captured["subject"] == "Your weekly portfolio update"
    assert "$500.00" in captured["html"]
    # No change/top-mover rows when there is no baseline.
    assert "This week" not in captured["html"]
    assert "Top mover" not in captured["html"]


def test_digest_unconfigured_is_noop(monkeypatch):
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    monkeypatch.delenv("ALERT_FROM_SENDER", raising=False)

    def _boom(*args, **kwargs):
        raise AssertionError("requests.post must not be called when unconfigured")

    monkeypatch.setattr("requests.post", _boom)
    assert send_weekly_digest_email("user@example.com", "Sam", _full_data(), "en") is False


def test_digest_missing_email_or_data_is_noop(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setenv("ALERT_FROM_SENDER", "alerts@stockpro.test")

    def _boom(*args, **kwargs):
        raise AssertionError("requests.post must not be called")

    monkeypatch.setattr("requests.post", _boom)
    assert send_weekly_digest_email("", "Sam", _full_data(), "en") is False
    assert send_weekly_digest_email("user@example.com", "Sam", {}, "en") is False


def test_digest_provider_error_returns_false(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setenv("ALERT_FROM_SENDER", "alerts@stockpro.test")
    captured = {}
    monkeypatch.setattr("requests.post", _capture_post(captured, status_code=500))
    assert send_weekly_digest_email("user@example.com", "Sam", _full_data(), "en") is False


# --------------------------------------------------------------------------- #
# Performance computation
# --------------------------------------------------------------------------- #

def _make_service(monkeypatch, holdings, week_ago):
    from portfolio.portfolio_service import PortfolioService

    svc = PortfolioService()
    monkeypatch.setattr(svc, "list_portfolios", lambda user_id=None: [{"portfolio_id": "p1"}])
    monkeypatch.setattr(svc, "get_holdings", lambda pid, with_prices=True: holdings)
    monkeypatch.setattr(svc, "_fetch_week_ago_prices", lambda h: week_ago)
    return svc


def test_weekly_performance_math(monkeypatch):
    holdings = [
        {"symbol": "AAPL", "asset_type": "stock", "currency": "USD",
         "total_quantity": Decimal("10"), "current_price": Decimal("110"), "price_available": True},
        {"symbol": "MSFT", "asset_type": "stock", "currency": "USD",
         "total_quantity": Decimal("5"), "current_price": Decimal("200"), "price_available": True},
    ]
    week_ago = {"AAPL": Decimal("100"), "MSFT": Decimal("210")}
    svc = _make_service(monkeypatch, holdings, week_ago)

    result = svc.get_weekly_performance("u1")

    assert result["total_value"] == Decimal("2100")  # 10*110 + 5*200
    # (2100 - 2050) / 2050 * 100
    assert round(float(result["week_change_pct"]), 2) == 2.44
    # AAPL +10% beats MSFT -4.76% on absolute move.
    assert result["top_mover"]["symbol"] == "AAPL"
    assert round(float(result["top_mover"]["pct"]), 1) == 10.0
    assert result["holdings_count"] == 2


def test_weekly_performance_new_holding_has_no_baseline(monkeypatch):
    """A holding bought this week (no week-ago price) counts toward value, not change."""
    holdings = [
        {"symbol": "AAPL", "asset_type": "stock", "currency": "USD",
         "total_quantity": Decimal("10"), "current_price": Decimal("110"), "price_available": True},
        {"symbol": "NEW", "asset_type": "stock", "currency": "USD",
         "total_quantity": Decimal("1"), "current_price": Decimal("50"), "price_available": True},
    ]
    week_ago = {"AAPL": Decimal("100")}  # NEW has no baseline
    svc = _make_service(monkeypatch, holdings, week_ago)

    result = svc.get_weekly_performance("u1")

    assert result["total_value"] == Decimal("1150")  # includes NEW
    # Change computed only from AAPL: (1100-1000)/1000 = +10%
    assert round(float(result["week_change_pct"]), 1) == 10.0
    assert result["top_mover"]["symbol"] == "AAPL"


def test_weekly_performance_includes_cash(monkeypatch):
    """Total value must include tracked cash so it matches the app's number."""
    from portfolio.portfolio_service import PortfolioService

    holdings = [
        {"symbol": "AAPL", "asset_type": "stock", "currency": "USD",
         "total_quantity": Decimal("10"), "current_price": Decimal("110"), "price_available": True},
    ]
    svc = PortfolioService()
    monkeypatch.setattr(
        svc, "list_portfolios",
        lambda user_id=None: [{"portfolio_id": "p1", "track_cash": True, "cash_balance": Decimal("500")}],
    )
    monkeypatch.setattr(svc, "get_holdings", lambda pid, with_prices=True: holdings)
    monkeypatch.setattr(svc, "_fetch_week_ago_prices", lambda h: {"AAPL": Decimal("100")})

    result = svc.get_weekly_performance("u1")

    # holdings 10*110 = 1100, plus 500 cash = 1600
    assert result["total_value"] == Decimal("1600")
    # Week % is measured on comparable holdings only, not diluted by cash.
    assert round(float(result["week_change_pct"]), 1) == 10.0


def test_weekly_performance_none_when_no_priced_holdings(monkeypatch):
    holdings = [
        {"symbol": "AAPL", "asset_type": "stock", "currency": "USD",
         "total_quantity": Decimal("10"), "current_price": Decimal("0"), "price_available": False},
    ]
    svc = _make_service(monkeypatch, holdings, {})
    assert svc.get_weekly_performance("u1") is None


def test_closest_on_or_before():
    from portfolio.portfolio_service import _closest_on_or_before

    prices = {
        date(2026, 6, 10): 1.0,
        date(2026, 6, 13): 2.0,
        date(2026, 6, 16): 3.0,
    }
    assert _closest_on_or_before(prices, date(2026, 6, 13)) == 2.0
    assert _closest_on_or_before(prices, date(2026, 6, 14)) == 2.0
    # Target before all data falls back to the earliest available price.
    assert _closest_on_or_before(prices, date(2026, 6, 9)) == 1.0
    assert _closest_on_or_before({}, date(2026, 6, 9)) is None


def test_week_ago_price_is_currency_consistent():
    """A TASE series quoted in agorot must not produce a bogus ~100x move
    against an app current price stored in shekels."""
    from portfolio.portfolio_service import _week_ago_price_from_series

    # Series in agorot (~100x the shekel current price), +1% over the week.
    closes = {date(2026, 6, 12): 495.0, date(2026, 6, 19): 500.0}
    current_price_shekels = Decimal("5.0")
    wap = _week_ago_price_from_series(current_price_shekels, closes, date(2026, 6, 12))

    # ratio 495/500 = 0.99 -> 5.0 * 0.99 = 4.95 (a sane ~+1% move, not a 100x drop)
    assert wap is not None
    assert abs(wap - Decimal("4.95")) < Decimal("0.001")

    # Degenerate inputs yield no baseline.
    assert _week_ago_price_from_series(Decimal("5.0"), {}, date(2026, 6, 12)) is None
    assert _week_ago_price_from_series(None, closes, date(2026, 6, 12)) is None
    assert _week_ago_price_from_series(
        Decimal("5.0"), {date(2026, 6, 19): 0.0}, date(2026, 6, 12)
    ) is None


# --------------------------------------------------------------------------- #
# Cron script orchestration
# --------------------------------------------------------------------------- #

def _load_script():
    path = os.path.join(
        os.path.dirname(__file__), "..", "scripts", "send_weekly_digest.py"
    )
    spec = importlib.util.spec_from_file_location("send_weekly_digest", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_script_resets_flag_on_failure_and_no_data(monkeypatch):
    """Sends each user; resets the flag on send failure and when there is no data."""
    monkeypatch.setenv("DATABASE_URL", "postgres://test")
    mod = _load_script()

    db = MagicMock()
    db.claim_weekly_digest_candidates.return_value = [
        {"user_id": "u1", "username": "Sam", "email": "a@x.test", "language": "en"},
        {"user_id": "u2", "username": "Dana", "email": "b@x.test", "language": "he"},
        {"user_id": "u3", "username": "Lee", "email": "c@x.test", "language": "en"},
    ]
    monkeypatch.setattr("database.get_database_manager", lambda: db)

    perf = {
        "u1": {"total_value": Decimal("100"), "week_change_pct": Decimal("1"),
               "top_mover": None, "holdings_count": 1},
        "u2": {"total_value": Decimal("200"), "week_change_pct": Decimal("2"),
               "top_mover": None, "holdings_count": 1},
        "u3": None,  # holdings sold since the claim
    }
    svc = MagicMock()
    svc.get_weekly_performance.side_effect = lambda uid: perf[uid]
    monkeypatch.setattr("portfolio.portfolio_service.get_portfolio_service", lambda: svc)

    # u1 send succeeds, u2 send fails.
    def _fake_send(email, username, data, language):
        return email == "a@x.test"

    monkeypatch.setattr("email_service.send_weekly_digest_email", _fake_send)

    rc = mod.main()
    assert rc == 0
    # u2 (send failed) and u3 (no data) get reset; u1 does not.
    reset_ids = {c.args[0] for c in db.reset_weekly_digest_flag.call_args_list}
    assert reset_ids == {"u2", "u3"}
