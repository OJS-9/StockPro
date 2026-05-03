"""Single source of truth for paid tier limits + Whop checkout URLs.

Tiers: free, starter, ultra. Each product in Whop has ONE checkout URL — the
customer picks monthly/yearly on Whop's page. Tier rides in metadata; cadence
is read from the membership webhook payload.
"""

import math
import os
from typing import Dict, Optional


TIER_LIMITS: Dict[str, Dict[str, float]] = {
    "free": {
        "reports_per_month": 3,
        "portfolios": 1,
        "watchlist_items": 10,
        "price_alerts": 5,
    },
    "starter": {
        "reports_per_month": 10,
        "portfolios": 3,
        "watchlist_items": 20,
        "price_alerts": 15,
    },
    "ultra": {
        "reports_per_month": math.inf,
        "portfolios": math.inf,
        "watchlist_items": math.inf,
        "price_alerts": math.inf,
    },
}


def _product_urls() -> Dict[str, Optional[str]]:
    """Re-read each call so monkeypatch works in tests."""
    return {
        "starter": os.getenv("WHOP_STARTER_URL"),
        "ultra": os.getenv("WHOP_ULTRA_URL"),
    }


def get_user_tier(user_id: str) -> str:
    """Read users.tier; default to 'free' on any miss."""
    from database import get_database_manager

    db = get_database_manager()
    user = db.get_user_by_id(user_id)
    if not user:
        return "free"
    tier = (user.get("tier") or "free").lower()
    if tier not in TIER_LIMITS:
        return "free"
    return tier


def get_limit(user_id: str, key: str) -> float:
    """Return the numeric cap for `key` for the user's current tier."""
    tier = get_user_tier(user_id)
    return TIER_LIMITS[tier].get(key, 0)


def get_all_limits(user_id: str) -> Dict[str, float]:
    """Full caps dict for the user's tier (for API responses).
    JSON cannot encode inf, so unlimited becomes -1."""
    tier = get_user_tier(user_id)
    out = {}
    for k, v in TIER_LIMITS[tier].items():
        out[k] = -1 if v == math.inf else int(v)
    return out


def plans_public() -> Dict[str, Dict[str, Optional[str]]]:
    """Product URLs + display prices for the SPA pricing page.

    Both monthly + yearly point to the same product URL; the customer
    picks the cadence on Whop's page.
    """
    urls = _product_urls()
    return {
        "starter": {
            "url": urls["starter"],
            "price_monthly": 19,
            "price_yearly": 190,
        },
        "ultra": {
            "url": urls["ultra"],
            "price_monthly": 59,
            "price_yearly": 590,
        },
    }


def build_checkout_url(tier: str, user_id: str) -> Optional[str]:
    """Append metadata params Whop will store on the resulting membership.

    Returns None if the product URL isn't configured in env.
    """
    from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

    tier = (tier or "").lower()
    if tier not in ("starter", "ultra"):
        return None
    base = _product_urls().get(tier)
    if not base:
        return None

    parts = urlsplit(base)
    existing = dict(parse_qsl(parts.query))
    existing.update({
        "metadata[user_id]": user_id,
        "metadata[tier]": tier,
    })
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(existing), parts.fragment))


def derive_cadence_from_webhook(payload: dict) -> str:
    """Whop puts the renewal interval somewhere on the membership/plan payload.

    We try a handful of common field names. Returns 'monthly' or 'yearly'.
    Defaults to 'monthly' if we can't figure it out — better than blocking
    activation over a missing field.
    """
    candidates = []
    for source in (payload, payload.get("plan") or {}, payload.get("membership") or {}):
        if not isinstance(source, dict):
            continue
        for key in (
            "renewal_period",
            "billing_period",
            "interval",
            "renewal_period_initial_interval",
            "renewal_period_initial_unit",
            "plan_type",
        ):
            v = source.get(key)
            if v:
                candidates.append(str(v).lower())

    blob = " ".join(candidates)
    if "year" in blob or "annual" in blob or "annually" in blob:
        return "yearly"
    return "monthly"
