"""Quota gates: portfolio create, watchlist add, alert create -> 402 at limit."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as c:
        yield c


@pytest.fixture
def logged_in(client):
    with client.session_transaction() as sess:
        sess["user_id"] = "u_test"
        sess["email"] = "q@test.com"
        sess["name"] = "Q User"


# ---- Portfolios: free tier cap = 1 ----

def test_portfolio_create_blocked_at_free_limit(client, logged_in):
    db = MagicMock()
    db.get_user_by_id.return_value = {"tier": "free"}
    db.count_user_portfolios.return_value = 1  # already at limit
    with patch("database.get_database_manager", return_value=db):
        r = client.post("/api/portfolios", json={"name": "Second"})
    assert r.status_code == 402
    body = r.get_json()
    assert body["error"] == "quota_exceeded"
    assert body["resource"] == "portfolios"


def test_portfolio_create_allowed_below_limit(client, logged_in):
    db = MagicMock()
    db.get_user_by_id.return_value = {"tier": "free"}
    db.count_user_portfolios.return_value = 0
    with patch("database.get_database_manager", return_value=db), \
         patch("app.get_portfolio_service") as mock_svc:
        svc = MagicMock()
        svc.create_portfolio.return_value = "pf_1"
        mock_svc.return_value = svc
        r = client.post("/api/portfolios", json={"name": "First", "track_cash": False})
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_portfolio_create_unlimited_for_ultra(client, logged_in):
    db = MagicMock()
    db.get_user_by_id.return_value = {"tier": "ultra"}
    # count_user_portfolios should NOT be checked for ultra (unlimited)
    with patch("database.get_database_manager", return_value=db), \
         patch("app.get_portfolio_service") as mock_svc:
        svc = MagicMock()
        svc.create_portfolio.return_value = "pf_X"
        mock_svc.return_value = svc
        r = client.post("/api/portfolios", json={"name": "many", "track_cash": False})
    assert r.status_code == 200


# ---- Alerts: free tier cap = 5 ----

def test_alert_create_blocked_at_free_limit(client, logged_in):
    db = MagicMock()
    db.get_user_by_id.return_value = {"tier": "free"}
    db.count_user_active_alerts.return_value = 5
    with patch("database.get_database_manager", return_value=db):
        r = client.post(
            "/api/alerts",
            json={"symbol": "AAPL", "direction": "above", "target_price": 200},
        )
    assert r.status_code == 402
    assert r.get_json()["resource"] == "price_alerts"


def test_alert_create_allowed_for_starter_under_15(client, logged_in):
    db = MagicMock()
    db.get_user_by_id.return_value = {"tier": "starter"}
    db.count_user_active_alerts.return_value = 14
    with patch("database.get_database_manager", return_value=db):
        r = client.post(
            "/api/alerts",
            json={"symbol": "AAPL", "direction": "above", "target_price": 200},
        )
    assert r.status_code == 200
    db.create_price_alert.assert_called_once()


# ---- Watchlist: free tier cap = 10 ----

def test_watchlist_add_blocked_at_free_limit(client, logged_in):
    db = MagicMock()
    db.get_user_by_id.return_value = {"tier": "free"}
    db.count_user_watchlist_items.return_value = 10

    wl_svc = MagicMock()
    wl_svc.db.get_watchlist.return_value = {"watchlist_id": "wl_1", "user_id": "u_test"}

    with patch("database.get_database_manager", return_value=db), \
         patch("app.get_watchlist_service", return_value=wl_svc):
        r = client.post("/api/watchlist/wl_1/symbol", json={"symbol": "TSLA"})

    assert r.status_code == 402
    assert r.get_json()["resource"] == "watchlist_items"
    wl_svc.add_symbol.assert_not_called()
