"""
Subscription tier definitions and enforcement helpers.

Single source of truth for:
  - plan pricing / display
  - resource limits per tier (reports, portfolios, watchlists, alerts, ...)
  - how Polar product IDs map back to a tier string stored in users.tier

users.tier values:
  'free'            -> default
  'starter_monthly' -> Starter @ $19/mo
  'starter_yearly'  -> Starter @ $210/yr
  'ultra_monthly'   -> Ultra @ $50/mo
  'ultra_yearly'    -> Ultra @ $520/yr
"""

import os
from typing import Any, Dict, Optional, Tuple

# Unlimited sentinel — checks treat None as "no limit".
UNLIMITED = None

# --- Resource limits per tier family ---------------------------------------

LIMITS: Dict[str, Dict[str, Optional[int]]] = {
    "free": {
        "reports_per_month": 3,
        "portfolios": 1,
        "holdings_per_portfolio": 15,
        "watchlists": 1,
        "items_per_watchlist": 10,
        "active_alerts": 3,
    },
    "starter": {
        "reports_per_month": 10,
        "portfolios": 3,
        "holdings_per_portfolio": 50,
        "watchlists": 5,
        "items_per_watchlist": 25,
        "active_alerts": 25,
    },
    "ultra": {
        "reports_per_month": 30,
        "portfolios": UNLIMITED,
        "holdings_per_portfolio": UNLIMITED,
        "watchlists": UNLIMITED,
        "items_per_watchlist": UNLIMITED,
        "active_alerts": UNLIMITED,
    },
}

# --- Plan catalog (displayed on Settings > Plan) ---------------------------

PLANS = [
    {
        "key": "starter_monthly",
        "family": "starter",
        "interval": "monthly",
        "name": "Starter",
        "price_usd": 19,
        "price_label": "$19 / month",
        "env_product_id": "POLAR_PRODUCT_STARTER_MONTHLY_ID",
    },
    {
        "key": "starter_yearly",
        "family": "starter",
        "interval": "yearly",
        "name": "Starter",
        "price_usd": 210,
        "price_label": "$210 / year",
        "env_product_id": "POLAR_PRODUCT_STARTER_YEARLY_ID",
    },
    {
        "key": "ultra_monthly",
        "family": "ultra",
        "interval": "monthly",
        "name": "Ultra",
        "price_usd": 50,
        "price_label": "$50 / month",
        "env_product_id": "POLAR_PRODUCT_ULTRA_MONTHLY_ID",
    },
    {
        "key": "ultra_yearly",
        "family": "ultra",
        "interval": "yearly",
        "name": "Ultra",
        "price_usd": 520,
        "price_label": "$520 / year",
        "env_product_id": "POLAR_PRODUCT_ULTRA_YEARLY_ID",
    },
]

VALID_PLAN_KEYS = {p["key"] for p in PLANS}


def plan_by_key(key: str) -> Optional[Dict[str, Any]]:
    for p in PLANS:
        if p["key"] == key:
            return p
    return None


def product_id_for_plan(key: str) -> str:
    plan = plan_by_key(key)
    if not plan:
        raise ValueError(f"Unknown plan: {key}")
    return os.getenv(plan["env_product_id"], "")


def tier_for_product_id(product_id: str) -> str:
    """Reverse lookup: Polar product_id -> users.tier value."""
    if not product_id:
        return "starter_monthly"
    for plan in PLANS:
        if product_id == os.getenv(plan["env_product_id"], ""):
            return plan["key"]
    return "starter_monthly"


def family_for_tier(tier: str) -> str:
    """Collapse tier (e.g. 'starter_yearly') to family ('starter') for limit lookup."""
    if not tier or tier == "free":
        return "free"
    if tier.startswith("ultra"):
        return "ultra"
    if tier.startswith("starter"):
        return "starter"
    return "free"


def limits_for_user(db: Any, user_id: str) -> Dict[str, Optional[int]]:
    """Resolve the current user's tier family and return its limits dict."""
    try:
        user = db.get_user_by_id(user_id) or {}
    except Exception:
        user = {}
    tier = user.get("tier") or "free"
    if not user.get("is_pro"):
        tier = "free"
    return LIMITS[family_for_tier(tier)]


def check_limit(
    db: Any, user_id: str, resource: str, current_count: int
) -> Tuple[bool, Optional[int]]:
    """
    Returns (allowed, limit).
      allowed = False means adding one more would exceed the cap.
      limit = None (UNLIMITED) -> always allowed.
    """
    limits = limits_for_user(db, user_id)
    limit = limits.get(resource)
    if limit is None:
        return True, None
    return current_count < limit, limit


def limit_error_payload(resource: str, limit: int) -> Dict[str, Any]:
    """Standard JSON body for a 403 tier-limit response."""
    friendly = {
        "portfolios": "portfolios",
        "holdings_per_portfolio": "holdings in this portfolio",
        "watchlists": "watchlists",
        "items_per_watchlist": "items in this watchlist",
        "active_alerts": "active price alerts",
        "reports_per_month": "research reports this month",
    }.get(resource, resource)
    return {
        "error": "tier_limit_exceeded",
        "resource": resource,
        "limit": limit,
        "message": f"You have reached your plan's limit of {limit} {friendly}. Upgrade to continue.",
        "upgrade_url": "/app/settings?section=plan",
    }
