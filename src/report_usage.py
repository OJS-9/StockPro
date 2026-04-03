"""Free-tier monthly research report quota (per user, per calendar month)."""

import os
from datetime import datetime, timezone
from typing import Optional, Tuple, Any


def get_free_tier_report_limit() -> int:
    """Default 3; 0 disables enforcement (no 403 on quota)."""
    raw = os.getenv("STOCKPRO_FREE_TIER_REPORT_LIMIT", "3")
    try:
        n = int(raw)
    except ValueError:
        return 3
    return max(0, n)


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

    If limit is 0, never exceeded (free enforcement off).
    Pro users never exceeded.
    """
    limit = get_free_tier_report_limit()
    if limit == 0:
        return False, 0, 0
    if db.user_is_pro(user_id):
        return False, limit, 0
    p = period or current_period_month()
    used = db.get_report_usage_count(user_id, p)
    return used >= limit, limit, used
