"""
Polar.sh subscription integration.

Flow:
  1. create_checkout_url() -> redirect user to Polar-hosted checkout
  2. Polar sends a webhook to /api/billing/webhook on lifecycle events
  3. handle_webhook_event() updates users.is_pro/tier + subscriptions row
  4. customer_portal_url() -> Polar-hosted portal for cancel / update card

No SDK — just httpx, matching the pattern in src/nimble_client.py.
"""

import hmac
import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

POLAR_TIMEOUT_SECONDS = float(os.getenv("POLAR_TIMEOUT_SECONDS", "15.0"))


def _api_base() -> str:
    env = (os.getenv("POLAR_ENV") or "production").lower()
    if env == "sandbox":
        return "https://sandbox-api.polar.sh"
    return "https://api.polar.sh"


def _headers() -> Dict[str, str]:
    token = os.getenv("POLAR_ACCESS_TOKEN", "")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _product_id(plan: str) -> str:
    from tiers import product_id_for_plan

    pid = product_id_for_plan(plan)
    if not pid:
        raise RuntimeError(f"Polar product ID not configured for plan={plan}")
    return pid


def _tier_for_product(product_id: str) -> str:
    from tiers import tier_for_product_id

    return tier_for_product_id(product_id)


def create_checkout_url(user_id: str, plan: str, success_url: str) -> str:
    """Create a Polar hosted checkout session and return its URL."""
    product_id = _product_id(plan)

    payload = {
        "product_id": product_id,
        "customer_external_id": user_id,
        "success_url": success_url,
        "metadata": {"user_id": user_id, "plan": plan},
    }
    with httpx.Client(timeout=POLAR_TIMEOUT_SECONDS) as client:
        resp = client.post(
            f"{_api_base()}/v1/checkouts/", headers=_headers(), json=payload
        )
        resp.raise_for_status()
        data = resp.json()
        url = data.get("url")
        if not url:
            raise RuntimeError(f"Polar checkout response missing url: {data}")
        return url


def customer_portal_url(customer_id: str) -> str:
    """Create a customer portal session URL for the given Polar customer."""
    payload = {"customer_id": customer_id}
    with httpx.Client(timeout=POLAR_TIMEOUT_SECONDS) as client:
        resp = client.post(
            f"{_api_base()}/v1/customer-sessions/",
            headers=_headers(),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        url = data.get("customer_portal_url") or data.get("url")
        if not url:
            raise RuntimeError(f"Polar portal response missing url: {data}")
        return url


def verify_webhook(body_bytes: bytes, signature_header: Optional[str]) -> bool:
    """
    Verify HMAC-SHA256 signature on a webhook payload.

    Polar sends the signature as a hex digest in the `webhook-signature` header
    (or `polar-signature` in older docs). We accept a plain hex digest.
    """
    secret = os.getenv("POLAR_WEBHOOK_SECRET", "")
    if not secret or not signature_header:
        return False
    expected = hmac.new(
        secret.encode("utf-8"), body_bytes, hashlib.sha256
    ).hexdigest()
    # Strip any prefix like "sha256=" just in case.
    sig = signature_header.strip()
    if "=" in sig:
        sig = sig.split("=", 1)[1]
    return hmac.compare_digest(expected, sig)


def _parse_period_end(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def handle_webhook_event(event: Dict[str, Any], db: Any) -> None:
    """
    Update users + subscriptions tables based on the Polar event.

    Supported event types (Polar):
      - subscription.created
      - subscription.updated
      - subscription.active
      - subscription.canceled
      - subscription.revoked
    """
    event_type = event.get("type") or ""
    data = event.get("data") or {}

    sub_id = data.get("id")
    customer = data.get("customer") or {}
    customer_id = data.get("customer_id") or customer.get("id")
    user_id = (
        data.get("customer_external_id")
        or customer.get("external_id")
        or (data.get("metadata") or {}).get("user_id")
    )
    product_id = data.get("product_id") or (data.get("product") or {}).get("id") or ""
    status = data.get("status") or ""
    current_period_end = _parse_period_end(data.get("current_period_end"))
    cancel_at_period_end = bool(data.get("cancel_at_period_end"))

    if not user_id:
        logger.warning("Polar webhook %s missing user_id; skipping", event_type)
        return

    tier = _tier_for_product(product_id)
    is_active = event_type in (
        "subscription.created",
        "subscription.updated",
        "subscription.active",
    ) and status in ("active", "trialing")

    is_revoked = event_type in ("subscription.canceled", "subscription.revoked") or status in (
        "canceled",
        "revoked",
        "unpaid",
    )

    if is_active:
        db.upsert_subscription(
            user_id=user_id,
            polar_subscription_id=sub_id,
            polar_customer_id=customer_id,
            product_id=product_id,
            status=status or "active",
            current_period_end=current_period_end,
            cancel_at_period_end=cancel_at_period_end,
        )
        db.set_user_pro(user_id=user_id, is_pro=True, tier=tier)
        logger.info("Polar: user %s is now PRO (%s)", user_id, tier)
    elif is_revoked:
        db.upsert_subscription(
            user_id=user_id,
            polar_subscription_id=sub_id,
            polar_customer_id=customer_id,
            product_id=product_id,
            status=status or "canceled",
            current_period_end=current_period_end,
            cancel_at_period_end=cancel_at_period_end,
        )
        db.set_user_pro(user_id=user_id, is_pro=False, tier="free")
        logger.info("Polar: user %s subscription ended", user_id)
    else:
        logger.info("Polar: unhandled event %s (status=%s)", event_type, status)
