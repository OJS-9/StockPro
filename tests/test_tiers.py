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
    monkeypatch.setenv("WHOP_STARTER_URL", "https://whop.com/x/starter/")
    monkeypatch.setenv("WHOP_ULTRA_URL", "https://whop.com/x/ultra/")
    p = tiers.plans_public()
    assert p["starter"]["url"] == "https://whop.com/x/starter/"
    assert p["ultra"]["url"] == "https://whop.com/x/ultra/"
    assert p["starter"]["price_monthly"] == 19
    assert p["ultra"]["price_yearly"] == 590


def test_build_checkout_url_appends_metadata(monkeypatch):
    monkeypatch.setenv("WHOP_STARTER_URL", "https://whop.com/org/starter/")
    url = tiers.build_checkout_url("starter", "user_abc")
    assert url is not None
    parts = urlsplit(url)
    assert parts.netloc == "whop.com"
    assert parts.path == "/org/starter/"
    qs = parse_qs(parts.query)
    assert qs["metadata[user_id]"] == ["user_abc"]
    assert qs["metadata[tier]"] == ["starter"]


def test_build_checkout_url_returns_none_when_unconfigured(monkeypatch):
    monkeypatch.delenv("WHOP_ULTRA_URL", raising=False)
    assert tiers.build_checkout_url("ultra", "user_x") is None


def test_build_checkout_url_rejects_bad_tier(monkeypatch):
    monkeypatch.setenv("WHOP_STARTER_URL", "https://whop.com/x/starter/")
    assert tiers.build_checkout_url("free", "u") is None
    assert tiers.build_checkout_url("bogus", "u") is None


def test_derive_cadence_yearly_from_renewal_period():
    assert tiers.derive_cadence_from_webhook({"renewal_period": "yearly"}) == "yearly"
    assert tiers.derive_cadence_from_webhook({"plan": {"renewal_period": "annual"}}) == "yearly"
    assert tiers.derive_cadence_from_webhook({"interval": "year"}) == "yearly"


def test_derive_cadence_monthly_default():
    assert tiers.derive_cadence_from_webhook({"renewal_period": "monthly"}) == "monthly"
    # missing field → default monthly (don't block activation)
    assert tiers.derive_cadence_from_webhook({}) == "monthly"
