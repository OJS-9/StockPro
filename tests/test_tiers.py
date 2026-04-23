"""Tier resolution + limit enforcement."""

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_family_for_tier():
    from tiers import family_for_tier

    assert family_for_tier("free") == "free"
    assert family_for_tier("") == "free"
    assert family_for_tier("starter_monthly") == "starter"
    assert family_for_tier("starter_yearly") == "starter"
    assert family_for_tier("ultra_monthly") == "ultra"
    assert family_for_tier("ultra_yearly") == "ultra"


def test_limits_for_free_user():
    from tiers import limits_for_user

    db = MagicMock()
    db.get_user_by_id.return_value = {"tier": "free", "is_pro": False}
    limits = limits_for_user(db, "u")
    assert limits["reports_per_month"] == 3
    assert limits["portfolios"] == 1
    assert limits["watchlists"] == 1
    assert limits["items_per_watchlist"] == 10
    assert limits["active_alerts"] == 3


def test_limits_for_pro_user():
    from tiers import limits_for_user

    db = MagicMock()
    db.get_user_by_id.return_value = {"tier": "starter_monthly", "is_pro": True}
    limits = limits_for_user(db, "u")
    assert limits["reports_per_month"] == 10
    assert limits["portfolios"] == 3
    assert limits["items_per_watchlist"] == 25
    assert limits["active_alerts"] == 25


def test_limits_for_ultra_user():
    from tiers import limits_for_user

    db = MagicMock()
    db.get_user_by_id.return_value = {"tier": "ultra_yearly", "is_pro": True}
    limits = limits_for_user(db, "u")
    assert limits["reports_per_month"] == 30
    assert limits["portfolios"] is None  # unlimited
    assert limits["items_per_watchlist"] is None


def test_check_limit_blocks_at_cap():
    from tiers import check_limit

    db = MagicMock()
    db.get_user_by_id.return_value = {"tier": "free", "is_pro": False}
    ok, limit = check_limit(db, "u", "portfolios", 1)
    assert ok is False
    assert limit == 1


def test_check_limit_allows_below_cap():
    from tiers import check_limit

    db = MagicMock()
    db.get_user_by_id.return_value = {"tier": "starter_monthly", "is_pro": True}
    ok, limit = check_limit(db, "u", "portfolios", 2)
    assert ok is True
    assert limit == 3


def test_check_limit_unlimited_always_ok():
    from tiers import check_limit

    db = MagicMock()
    db.get_user_by_id.return_value = {"tier": "ultra_monthly", "is_pro": True}
    ok, limit = check_limit(db, "u", "portfolios", 9999)
    assert ok is True
    assert limit is None


def test_report_quota_tier_aware(monkeypatch):
    # ensure env override is inactive
    monkeypatch.delenv("STOCKPRO_FREE_TIER_REPORT_LIMIT", raising=False)

    from report_usage import quota_exceeded_for_user

    db = MagicMock()

    # Free user at 3 reports -> exceeded
    db.get_user_by_id.return_value = {"tier": "free", "is_pro": False}
    db.get_report_usage_count.return_value = 3
    exceeded, limit, used = quota_exceeded_for_user(db, "u")
    assert exceeded is True
    assert limit == 3
    assert used == 3

    # Pro user at 9 reports -> fine, 10 cap
    db.get_user_by_id.return_value = {"tier": "starter_monthly", "is_pro": True}
    db.get_report_usage_count.return_value = 9
    exceeded, limit, _ = quota_exceeded_for_user(db, "u")
    assert exceeded is False
    assert limit == 10

    # Ultra user at 29 -> fine, 30 cap
    db.get_user_by_id.return_value = {"tier": "ultra_monthly", "is_pro": True}
    db.get_report_usage_count.return_value = 29
    exceeded, limit, _ = quota_exceeded_for_user(db, "u")
    assert exceeded is False
    assert limit == 30

    # Ultra user at 30 -> exceeded
    db.get_report_usage_count.return_value = 30
    exceeded, _, _ = quota_exceeded_for_user(db, "u")
    assert exceeded is True
