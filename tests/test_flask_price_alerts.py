"""
Flask tests for /api/alerts (price alert CRUD).
"""

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
        sess["user_id"] = str(uuid.uuid4())
        sess["email"] = "alerts@test.com"
        sess["name"] = "Alerts User"


def test_list_alerts_requires_login(client):
    r = client.get("/api/alerts")
    assert r.status_code == 302


def test_list_alerts_empty(client, logged_in):
    with patch("database.get_database_manager") as mock_db:
        db = MagicMock()
        db.list_price_alerts_for_user.return_value = []
        mock_db.return_value = db
        r = client.get("/api/alerts")
    assert r.status_code == 200
    data = r.get_json()
    assert data["success"] is True
    assert data["alerts"] == []


def test_create_alert_success(client, logged_in):
    uid = None
    with client.session_transaction() as sess:
        uid = sess["user_id"]
    with patch("database.get_database_manager") as mock_db:
        db = MagicMock()
        mock_db.return_value = db
        r = client.post(
            "/api/alerts",
            json={
                "symbol": "AAPL",
                "direction": "above",
                "target_price": 200.5,
                "asset_type": "stock",
            },
        )
    assert r.status_code == 200
    data = r.get_json()
    assert data["success"] is True
    assert "alert_id" in data
    db.create_price_alert.assert_called_once()
    call_kw = db.create_price_alert.call_args[1]
    assert call_kw["user_id"] == uid
    assert call_kw["symbol"] == "AAPL"
    assert call_kw["direction"] == "above"
    assert call_kw["target_price"] == 200.5
    assert call_kw["asset_type"] == "stock"


def test_create_alert_validation(client, logged_in):
    r = client.post("/api/alerts", json={"direction": "above", "target_price": 1})
    assert r.status_code == 400
    r = client.post("/api/alerts", json={"symbol": "X", "direction": "sideways"})
    assert r.status_code == 400


def test_delete_alert(client, logged_in):
    aid = str(uuid.uuid4())
    with client.session_transaction() as sess:
        uid = sess["user_id"]
    with patch("database.get_database_manager") as mock_db:
        db = MagicMock()
        db.delete_price_alert.return_value = True
        mock_db.return_value = db
        r = client.delete(f"/api/alerts/{aid}")
    assert r.status_code == 200
    db.delete_price_alert.assert_called_once_with(aid, uid)


def test_delete_alert_not_found(client, logged_in):
    with patch("database.get_database_manager") as mock_db:
        db = MagicMock()
        db.delete_price_alert.return_value = False
        mock_db.return_value = db
        r = client.delete("/api/alerts/not-real")
    assert r.status_code == 404


def test_patch_alert_active(client, logged_in):
    aid = str(uuid.uuid4())
    with client.session_transaction() as sess:
        uid = sess["user_id"]
    with patch("database.get_database_manager") as mock_db:
        db = MagicMock()
        db.set_price_alert_active.return_value = True
        mock_db.return_value = db
        r = client.patch(f"/api/alerts/{aid}", json={"active": False})
    assert r.status_code == 200
    db.set_price_alert_active.assert_called_once_with(aid, uid, False)


def test_list_notifications_requires_login(client):
    r = client.get("/api/alerts/notifications")
    assert r.status_code == 302


def test_list_notifications_empty(client, logged_in):
    with patch("database.get_database_manager") as mock_db:
        db = MagicMock()
        db.list_price_alert_notifications_for_user.return_value = []
        db.count_unread_price_alert_notifications.return_value = 0
        mock_db.return_value = db
        r = client.get("/api/alerts/notifications")
    assert r.status_code == 200
    data = r.get_json()
    assert data["success"] is True
    assert data["notifications"] == []
    assert data["unread_count"] == 0


def test_patch_notification_read(client, logged_in):
    nid = str(uuid.uuid4())
    with client.session_transaction() as sess:
        uid = sess["user_id"]
    with patch("database.get_database_manager") as mock_db:
        db = MagicMock()
        db.mark_price_alert_notification_read.return_value = True
        mock_db.return_value = db
        r = client.patch(f"/api/alerts/notifications/{nid}", json={"read": True})
    assert r.status_code == 200
    db.mark_price_alert_notification_read.assert_called_once_with(nid, uid)
