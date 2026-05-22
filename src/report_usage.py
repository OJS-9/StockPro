"""Per-user monthly research report quota (tier-aware)."""

import math
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

    Limit comes from the user's tier (tiers.TIER_LIMITS). Ultra = unlimited.
    A free-tier global override of 0 disables enforcement entirely.
    """
    # Hard global off-switch (env)
    if get_free_tier_report_limit() == 0:
        return False, 0, 0

    from tiers import get_limit

    limit_f = get_limit(user_id, "reports_per_month")
    if limit_f == math.inf:
        return False, -1, 0

    limit = int(limit_f)
    p = period or current_period_month()
    used = db.get_report_usage_count(user_id, p)
    return used >= limit, limit, used
