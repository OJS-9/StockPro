"""Single source of truth for paid tier limits + Whop checkout URLs.

Tiers: free, starter, ultra. Each tier has 2 cadences (monthly, yearly), each
configured as its own Whop product with a separate checkout URL. The SPA
picks the URL based on the toggle; tier+cadence ride along in metadata.
"""

import math
import os
from typing import Dict, Optional, Tuple


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


def _checkout_urls() -> Dict[str, Optional[str]]:
    """Re-read each call so monkeypatch works in tests."""
    return {
        "starter_monthly": os.getenv("WHOP_STARTER_MONTHLY_URL"),
        "starter_yearly": os.getenv("WHOP_STARTER_YEARLY_URL"),
        "ultra_monthly": os.getenv("WHOP_ULTRA_MONTHLY_URL"),
        "ultra_yearly": os.getenv("WHOP_ULTRA_YEARLY_URL"),
    }


def get_user_tier(user_id: str) -> str:
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
    tier = get_user_tier(user_id)
    return TIER_LIMITS[tier].get(key, 0)


def get_all_limits(user_id: str) -> Dict[str, float]:
    tier = get_user_tier(user_id)
    out = {}
    for k, v in TIER_LIMITS[tier].items():
        out[k] = -1 if v == math.inf else int(v)
    return out


def plans_public() -> Dict[str, Dict[str, Optional[object]]]:
    """Plan checkout URLs + display prices for the SPA pricing page."""
    urls = _checkout_urls()
    return {
        "starter": {
            "monthly_url": urls["starter_monthly"],
            "yearly_url": urls["starter_yearly"],
            "price_monthly": _price("WHOP_STARTER_PRICE_MONTHLY", 19),
            "price_yearly": _price("WHOP_STARTER_PRICE_YEARLY", 190),
        },
        "ultra": {
            "monthly_url": urls["ultra_monthly"],
            "yearly_url": urls["ultra_yearly"],
            "price_monthly": _price("WHOP_ULTRA_PRICE_MONTHLY", 59),
            "price_yearly": _price("WHOP_ULTRA_PRICE_YEARLY", 590),
        },
    }


def _price(env_key: str, default: int) -> int:
    raw = os.getenv(env_key)
    if not raw:
        return default
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return default


def resolve_url(tier: str, cadence: str) -> Optional[Tuple[str, str, str]]:
    tier = (tier or "").lower()
    cadence = (cadence or "").lower()
    if tier not in ("starter", "ultra") or cadence not in ("monthly", "yearly"):
        return None
    base = _checkout_urls().get(f"{tier}_{cadence}")
    if not base:
        return None
    return tier, cadence, base


def build_checkout_url(tier: str, cadence: str, user_id: str) -> Optional[str]:
    """Append metadata Whop will store on the resulting membership."""
    from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

    resolved = resolve_url(tier, cadence)
    if not resolved:
        return None
    _, _, base = resolved

    parts = urlsplit(base)
    existing = dict(parse_qsl(parts.query))
    existing.update({
        "metadata[user_id]": user_id,
        "metadata[tier]": tier,
        "metadata[cadence]": cadence,
    })
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(existing), parts.fragment))
