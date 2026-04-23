"""Monthly research report quota (per user, per calendar month) — tier-aware."""

import os
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from tiers import LIMITS, family_for_tier


def get_free_tier_report_limit() -> int:
    """Env override for the Free tier only; 0 disables enforcement entirely."""
    raw = os.getenv("STOCKPRO_FREE_TIER_REPORT_LIMIT")
    if raw is None:
        return LIMITS["free"]["reports_per_month"] or 0
    try:
        n = int(raw)
    except ValueError:
        return LIMITS["free"]["reports_per_month"] or 0
    return max(0, n)


def _limit_for_user(db: Any, user_id: str) -> int:
    """Resolve reports-per-month cap based on the user's tier (0 = disabled)."""
    try:
        user = db.get_user_by_id(user_id)
    except Exception:
        user = None
    if not isinstance(user, dict):
        # Legacy callers (or tests) may not expose get_user_by_id; fall back to
        # user_is_pro() + env override.
        try:
            is_pro = bool(db.user_is_pro(user_id))
        except Exception:
            is_pro = False
        if is_pro:
            return int(LIMITS["starter"]["reports_per_month"] or 0)
        env_override = os.getenv("STOCKPRO_FREE_TIER_REPORT_LIMIT")
        if env_override is not None:
            try:
                return max(0, int(env_override))
            except ValueError:
                pass
        return int(LIMITS["free"]["reports_per_month"] or 0)

    tier = user.get("tier") or "free"
    if not user.get("is_pro"):
        tier = "free"
        env_override = os.getenv("STOCKPRO_FREE_TIER_REPORT_LIMIT")
        if env_override is not None:
            try:
                return max(0, int(env_override))
            except ValueError:
                pass
    family = family_for_tier(tier)
    limit = LIMITS[family]["reports_per_month"]
    return 0 if limit is None else int(limit)


def current_period_month() -> str:
    """UTC month bucket YYYY-MM (matches monthly reset without cron)."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


def quota_exceeded_for_user(
    db: Any,
    user_id: str,
    *,
    period: Optional[str] = None,
) -> Tuple[bool, int, int]:
    """
    Returns (exceeded, limit, used).

    - limit=0 means enforcement disabled (never exceeded).
    - Uses the user's tier (free: 3, pro: 10, ultra: 30) — Ultra users still hit a cap.
    """
    limit = _limit_for_user(db, user_id)
    if limit == 0:
        return False, 0, 0
    p = period or current_period_month()
    used = db.get_report_usage_count(user_id, p)
    return used >= limit, limit, used
