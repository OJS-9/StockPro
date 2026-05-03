"""Whop webhook signature verification + lightweight HTTP client.

Whop signs webhooks with HMAC-SHA256 over `webhook_id.timestamp.body`,
keyed by a base64-encoded secret. We don't need the full SDK — just verify
sigs and call /users/{id}/access/{resource_id} for fallback re-checks.
"""

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict

import httpx


WHOP_API_BASE = "https://api.whop.com/v5"
SIG_TOLERANCE_SEC = 5 * 60  # reject webhooks older than 5 min (replay protection)


class WhopSignatureError(Exception):
    """Raised when a webhook signature is missing, malformed, or invalid."""


def _secret_bytes() -> bytes:
    raw = os.getenv("WHOP_WEBHOOK_SECRET", "")
    if not raw:
        raise WhopSignatureError("WHOP_WEBHOOK_SECRET not set")
    try:
        return base64.b64decode(raw)
    except Exception as e:
        raise WhopSignatureError(f"WHOP_WEBHOOK_SECRET not valid base64: {e}")


def verify_webhook(body: bytes, headers: Dict[str, str]) -> Dict[str, Any]:
    """Verify the HMAC sig + freshness; return the parsed JSON event.

    Whop headers (case-insensitive):
      whop-signature   = "v1=<hex_hmac>"
      whop-timestamp   = unix seconds
      whop-webhook-id  = uuid
    """
    # Normalize header lookup
    h = {k.lower(): v for k, v in headers.items()}
    sig_header = h.get("whop-signature", "")
    timestamp = h.get("whop-timestamp", "")
    webhook_id = h.get("whop-webhook-id", "")

    if not sig_header or not timestamp or not webhook_id:
        raise WhopSignatureError("Missing Whop signature headers")

    # Format: "v1=<hex>"
    parts = dict(p.split("=", 1) for p in sig_header.split(",") if "=" in p)
    provided = parts.get("v1")
    if not provided:
        raise WhopSignatureError("Bad signature header format")

    # Replay protection
    try:
        ts = int(timestamp)
    except ValueError:
        raise WhopSignatureError("Bad timestamp")
    if abs(time.time() - ts) > SIG_TOLERANCE_SEC:
        raise WhopSignatureError("Timestamp outside tolerance window")

    # Compute expected sig over "webhook_id.timestamp.body"
    body_str = body.decode("utf-8") if isinstance(body, (bytes, bytearray)) else body
    signed_payload = f"{webhook_id}.{timestamp}.{body_str}".encode("utf-8")
    expected = hmac.new(_secret_bytes(), signed_payload, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, provided):
        raise WhopSignatureError("Signature mismatch")

    try:
        return json.loads(body_str)
    except json.JSONDecodeError as e:
        raise WhopSignatureError(f"Body not valid JSON: {e}")


def check_access(whop_user_id: str, resource_id: str) -> Dict[str, Any]:
    """Authoritative re-check via Whop API (used as a fallback if a webhook
    is missed). Returns the raw response dict; caller decides what to do."""
    api_key = os.getenv("WHOP_API_KEY")
    if not api_key:
        raise RuntimeError("WHOP_API_KEY not set")
    url = f"{WHOP_API_BASE}/users/{whop_user_id}/access/{resource_id}"
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(url, headers={"Authorization": f"Bearer {api_key}"})
        resp.raise_for_status()
        return resp.json()
