"""Tier limit lookups + Whop checkout URL helpers."""

import math
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import tiers


def test_tier_limits_shape():
    for tier in ("free", "starter", "ultra"):
        assert tier in tiers.TIER_LIMITS
        for k in ("reports_per_month", "portfolios", "watchlist_items", "price_alerts"):
            assert k in tiers.TIER_LIMITS[tier]


def test_ultra_unlimited():
    for v in tiers.TIER_LIMITS["ultra"].values():
        assert v == math.inf


def test_starter_caps():
    s = tiers.TIER_LIMITS["starter"]
    assert s["reports_per_month"] == 10
    assert s["portfolios"] == 3
    assert s["watchlist_items"] == 20
    assert s["price_alerts"] == 15


def test_get_user_tier_default_when_missing():
    db = MagicMock()
    db.get_user_by_id.return_value = None
    with patch("database.get_database_manager", return_value=db):
        assert tiers.get_user_tier("u_nope") == "free"


def test_get_user_tier_normalizes_unknown_value():
    db = MagicMock()
    db.get_user_by_id.return_value = {"tier": "enterprise"}
    with patch("database.get_database_manager", return_value=db):
        assert tiers.get_user_tier("u1") == "free"


def test_get_limit_starter():
    db = MagicMock()
    db.get_user_by_id.return_value = {"tier": "starter"}
    with patch("database.get_database_manager", return_value=db):
        assert tiers.get_limit("u1", "portfolios") == 3
        assert tiers.get_limit("u1", "reports_per_month") == 10


def test_get_all_limits_serializes_inf_as_minus_one():
    db = MagicMock()
    db.get_user_by_id.return_value = {"tier": "ultra"}
    with patch("database.get_database_manager", return_value=db):
        out = tiers.get_all_limits("u1")
        for v in out.values():
            assert v == -1


def test_plans_public_reads_env(monkeypatch):
    monkeypatch.setenv("WHOP_STARTER_MONTHLY_URL", "https://whop.com/x/starter-m/")
    monkeypatch.setenv("WHOP_STARTER_YEARLY_URL", "https://whop.com/x/starter-y/")
    monkeypatch.setenv("WHOP_ULTRA_MONTHLY_URL", "https://whop.com/x/ultra-m/")
    monkeypatch.setenv("WHOP_ULTRA_YEARLY_URL", "https://whop.com/x/ultra-y/")
    p = tiers.plans_public()
    assert p["starter"]["monthly_url"] == "https://whop.com/x/starter-m/"
    assert p["starter"]["yearly_url"] == "https://whop.com/x/starter-y/"
    assert p["ultra"]["monthly_url"] == "https://whop.com/x/ultra-m/"
    assert p["ultra"]["yearly_url"] == "https://whop.com/x/ultra-y/"


def test_price_overrides_via_env(monkeypatch):
    monkeypatch.setenv("WHOP_STARTER_PRICE_YEARLY", "180")
    monkeypatch.setenv("WHOP_ULTRA_PRICE_YEARLY", "550")
    p = tiers.plans_public()
    assert p["starter"]["price_yearly"] == 180
    assert p["ultra"]["price_yearly"] == 550
    # Non-overridden falls back to defaults
    assert p["starter"]["price_monthly"] == 19
    assert p["ultra"]["price_monthly"] == 59


def test_build_checkout_url_appends_metadata(monkeypatch):
    monkeypatch.setenv("WHOP_STARTER_YEARLY_URL", "https://whop.com/org/starter-y/")
    url = tiers.build_checkout_url("starter", "yearly", "user_abc")
    assert url is not None
    parts = urlsplit(url)
    assert parts.netloc == "whop.com"
    assert parts.path == "/org/starter-y/"
    qs = parse_qs(parts.query)
    assert qs["metadata[user_id]"] == ["user_abc"]
    assert qs["metadata[tier]"] == ["starter"]
    assert qs["metadata[cadence]"] == ["yearly"]


def test_build_checkout_url_returns_none_when_unconfigured(monkeypatch):
    monkeypatch.delenv("WHOP_ULTRA_YEARLY_URL", raising=False)
    assert tiers.build_checkout_url("ultra", "yearly", "user_x") is None


def test_build_checkout_url_rejects_bad_inputs(monkeypatch):
    monkeypatch.setenv("WHOP_STARTER_MONTHLY_URL", "https://whop.com/x/starter-m/")
    assert tiers.build_checkout_url("free", "monthly", "u") is None
    assert tiers.build_checkout_url("starter", "weekly", "u") is None
