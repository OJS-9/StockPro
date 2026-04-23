"""Polar.sh webhook signature verification + event handler."""

import hashlib
import hmac
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture(autouse=True)
def _polar_env(monkeypatch):
    monkeypatch.setenv("POLAR_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setenv("POLAR_PRODUCT_STARTER_MONTHLY_ID", "prod_m")
    monkeypatch.setenv("POLAR_PRODUCT_STARTER_YEARLY_ID", "prod_y")
    monkeypatch.setenv("POLAR_PRODUCT_ULTRA_MONTHLY_ID", "prod_um")
    monkeypatch.setenv("POLAR_PRODUCT_ULTRA_YEARLY_ID", "prod_uy")


def _sign(body: bytes, secret: str = "test-secret") -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_verify_webhook_good_signature():
    from billing.polar_service import verify_webhook

    body = b'{"type": "subscription.active"}'
    assert verify_webhook(body, _sign(body)) is True


def test_verify_webhook_bad_signature():
    from billing.polar_service import verify_webhook

    body = b'{"type": "subscription.active"}'
    assert verify_webhook(body, "deadbeef") is False


def test_verify_webhook_missing_signature():
    from billing.polar_service import verify_webhook

    assert verify_webhook(b"{}", None) is False


def test_handle_event_activates_pro_monthly():
    from billing.polar_service import handle_webhook_event

    db = MagicMock()
    event = {
        "type": "subscription.active",
        "data": {
            "id": "sub_123",
            "customer_id": "cus_1",
            "customer_external_id": "user_1",
            "product_id": "prod_m",
            "status": "active",
            "current_period_end": "2026-05-20T00:00:00Z",
            "cancel_at_period_end": False,
        },
    }
    handle_webhook_event(event, db)
    db.upsert_subscription.assert_called_once()
    db.set_user_pro.assert_called_once_with(
        user_id="user_1", is_pro=True, tier="starter_monthly"
    )


def test_handle_event_activates_pro_yearly():
    from billing.polar_service import handle_webhook_event

    db = MagicMock()
    event = {
        "type": "subscription.created",
        "data": {
            "id": "sub_y",
            "customer_id": "cus_2",
            "customer_external_id": "user_2",
            "product_id": "prod_y",
            "status": "active",
        },
    }
    handle_webhook_event(event, db)
    db.set_user_pro.assert_called_once_with(
        user_id="user_2", is_pro=True, tier="starter_yearly"
    )


def test_handle_event_activates_ultra_monthly():
    from billing.polar_service import handle_webhook_event

    db = MagicMock()
    event = {
        "type": "subscription.active",
        "data": {
            "id": "sub_u",
            "customer_id": "cus_u",
            "customer_external_id": "user_u",
            "product_id": "prod_um",
            "status": "active",
        },
    }
    handle_webhook_event(event, db)
    db.set_user_pro.assert_called_once_with(
        user_id="user_u", is_pro=True, tier="ultra_monthly"
    )


def test_handle_event_cancels_subscription():
    from billing.polar_service import handle_webhook_event

    db = MagicMock()
    event = {
        "type": "subscription.canceled",
        "data": {
            "id": "sub_c",
            "customer_id": "cus_3",
            "customer_external_id": "user_3",
            "product_id": "prod_m",
            "status": "canceled",
        },
    }
    handle_webhook_event(event, db)
    db.set_user_pro.assert_called_once_with(
        user_id="user_3", is_pro=False, tier="free"
    )


def test_handle_event_skips_without_user_id():
    from billing.polar_service import handle_webhook_event

    db = MagicMock()
    handle_webhook_event({"type": "subscription.active", "data": {}}, db)
    db.set_user_pro.assert_not_called()


def test_flask_webhook_rejects_bad_signature(monkeypatch):
    monkeypatch.setenv("TESTING", "1")
    from app import app as flask_app

    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    client = flask_app.test_client()

    body = json.dumps({"type": "subscription.active"}).encode()
    resp = client.post(
        "/api/billing/webhook",
        data=body,
        headers={"webhook-signature": "bad", "Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_flask_webhook_accepts_good_signature(monkeypatch):
    from app import app as flask_app
    import billing.polar_service as polar_service

    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    client = flask_app.test_client()

    called = {}

    def fake_handle(event, db):
        called["event_type"] = event.get("type")

    monkeypatch.setattr(polar_service, "handle_webhook_event", fake_handle)

    body = json.dumps({"type": "subscription.active", "data": {}}).encode()
    resp = client.post(
        "/api/billing/webhook",
        data=body,
        headers={"webhook-signature": _sign(body), "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert called["event_type"] == "subscription.active"
