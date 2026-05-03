"""Whop webhook signature verification + event routing."""

import base64
import hashlib
import hmac
import json
import time
from unittest.mock import MagicMock, patch

import pytest

from app import app
from billing.whop_service import verify_webhook, WhopSignatureError


SECRET_RAW = b"super-secret-bytes-here-32-chars-x"
SECRET_B64 = base64.b64encode(SECRET_RAW).decode()


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("WHOP_WEBHOOK_SECRET", SECRET_B64)
    monkeypatch.setenv("WHOP_STARTER_URL", "https://whop.com/x/starter/")
    monkeypatch.setenv("WHOP_ULTRA_URL", "https://whop.com/x/ultra/")


@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as c:
        yield c


def _sign(body: bytes, webhook_id: str = "wh_1", ts: int | None = None) -> dict:
    ts = ts or int(time.time())
    payload = f"{webhook_id}.{ts}.{body.decode()}".encode()
    sig = hmac.new(SECRET_RAW, payload, hashlib.sha256).hexdigest()
    return {
        "Whop-Signature": f"v1={sig}",
        "Whop-Timestamp": str(ts),
        "Whop-Webhook-Id": webhook_id,
        "Content-Type": "application/json",
    }


# ----- verify_webhook unit tests -----

def test_verify_webhook_accepts_valid_sig():
    body = b'{"action":"membership.activated","data":{}}'
    headers = _sign(body)
    parsed = verify_webhook(body, headers)
    assert parsed["action"] == "membership.activated"


def test_verify_webhook_rejects_bad_sig():
    body = b'{"hi":"there"}'
    headers = _sign(body)
    headers["Whop-Signature"] = "v1=deadbeef"
    with pytest.raises(WhopSignatureError):
        verify_webhook(body, headers)


def test_verify_webhook_rejects_old_timestamp():
    body = b'{"hi":"there"}'
    headers = _sign(body, ts=int(time.time()) - 60 * 60)  # 1h old
    with pytest.raises(WhopSignatureError):
        verify_webhook(body, headers)


def test_verify_webhook_rejects_missing_headers():
    with pytest.raises(WhopSignatureError):
        verify_webhook(b"{}", {})


# ----- Flask route handler tests -----

def _post(client, body_dict, **header_overrides):
    body = json.dumps(body_dict).encode()
    headers = _sign(body)
    headers.update(header_overrides)
    return client.post("/api/billing/webhook", data=body, headers=headers)


def test_webhook_rejects_bad_signature(client):
    r = client.post(
        "/api/billing/webhook",
        data=b"{}",
        headers={"Whop-Signature": "v1=bad", "Whop-Timestamp": str(int(time.time())), "Whop-Webhook-Id": "x"},
    )
    assert r.status_code == 401


def test_webhook_membership_activated_sets_tier(client):
    payload = {
        "action": "membership.activated",
        "data": {
            "id": "mem_123",
            "plan_id": "plan_anything",
            "metadata": {"user_id": "user_abc", "tier": "starter"},
            "renewal_period": "monthly",
            "expires_at": "2027-01-01T00:00:00Z",
        },
    }
    db = MagicMock()
    with patch("database.get_database_manager", return_value=db):
        r = _post(client, payload)

    assert r.status_code == 200
    db.upsert_subscription.assert_called_once()
    call_kwargs = db.upsert_subscription.call_args.kwargs
    assert call_kwargs["user_id"] == "user_abc"
    assert call_kwargs["whop_membership_id"] == "mem_123"
    assert call_kwargs["tier"] == "starter"
    assert call_kwargs["cadence"] == "monthly"
    db.set_user_tier.assert_called_once_with("user_abc", "starter")


def test_webhook_membership_yearly_ultra(client):
    payload = {
        "action": "membership.activated",
        "data": {
            "id": "mem_yr",
            "metadata": {"user_id": "u9", "tier": "ultra"},
            "renewal_period": "yearly",
        },
    }
    db = MagicMock()
    with patch("database.get_database_manager", return_value=db):
        r = _post(client, payload)
    assert r.status_code == 200
    kw = db.upsert_subscription.call_args.kwargs
    assert kw["tier"] == "ultra"
    assert kw["cadence"] == "yearly"


def test_webhook_membership_deactivated_downgrades(client):
    payload = {
        "action": "membership.deactivated",
        "data": {"id": "mem_456", "metadata": {"user_id": "u_x"}},
    }
    db = MagicMock()
    db.get_subscription_user.return_value = "u_x"
    with patch("database.get_database_manager", return_value=db):
        r = _post(client, payload)
    assert r.status_code == 200
    db.set_subscription_status.assert_called_once_with("mem_456", "canceled")
    db.set_user_tier.assert_called_once_with("u_x", "free")


def test_webhook_missing_tier_metadata_400(client):
    payload = {
        "action": "membership.activated",
        "data": {"id": "mem_77", "metadata": {"user_id": "u1"}},  # no tier/cadence
    }
    db = MagicMock()
    with patch("database.get_database_manager", return_value=db):
        r = _post(client, payload)
    assert r.status_code == 400
    db.upsert_subscription.assert_not_called()


def test_webhook_unknown_event_type_ignored(client):
    payload = {"action": "something_else", "data": {}}
    db = MagicMock()
    with patch("database.get_database_manager", return_value=db):
        r = _post(client, payload)
    assert r.status_code == 200
    j = r.get_json()
    assert j.get("ignored") == "something_else"
