"""Settings API contract tests — the SPA billing/return page polls this for tier."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent / "src"))


@pytest.fixture
def api_app():
    from app import app as flask_app

    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    flask_app.config["SECRET_KEY"] = "test-settings-secret"
    return flask_app


@pytest.fixture
def api_client(api_app):
    return api_app.test_client()


def _login(client, user_id="u_test"):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def test_settings_returns_tier_and_limits_for_free(api_client):
    db = MagicMock()
    db.get_user_by_id.return_value = {
        "user_id": "u_test",
        "username": "tester",
        "is_pro": False,
        "tier": "free",
        "preferences": {},
    }
    _login(api_client)
    with patch("database.get_database_manager", return_value=db):
        resp = api_client.get("/api/settings")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["profile"]["tier"] == "free"
    limits = body["profile"]["tier_limits"]
    # Contract the SPA depends on: every gated quota key is present
    for key in ("reports_per_month", "portfolios", "watchlist_items", "price_alerts"):
        assert key in limits


def test_settings_returns_tier_and_limits_for_starter(api_client):
    db = MagicMock()
    db.get_user_by_id.return_value = {
        "user_id": "u_test",
        "username": "tester",
        "is_pro": True,
        "tier": "starter",
        "preferences": {},
    }
    _login(api_client)
    with patch("database.get_database_manager", return_value=db):
        resp = api_client.get("/api/settings")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["profile"]["tier"] == "starter"
    limits = body["profile"]["tier_limits"]
    assert limits["reports_per_month"] == 10
    assert limits["portfolios"] == 3
    assert limits["watchlist_items"] == 20
    assert limits["price_alerts"] == 15
