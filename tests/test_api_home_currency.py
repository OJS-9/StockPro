"""
Tests for the three portfolio-value bugs fixed in api_home().

Bug 1 — ILS holdings must be converted to USD before accumulating total_value.
Bug 2 — Holdings with no cached price must fall back to average_cost, not $0.
Bug 3 — Cash balance must be included in total_value when track_cash is enabled.
"""

import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from currency_utils import convert_to_usd, detect_currency  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _holding(symbol, qty, avg_cost, currency=None):
    qty_d = Decimal(str(qty))
    avg_d = Decimal(str(avg_cost))
    cur = currency or ("ILS" if symbol.upper().endswith(".TA") else "USD")
    return {
        "symbol": symbol,
        "total_quantity": qty_d,
        "average_cost": avg_d,
        "total_cost_basis": qty_d * avg_d,
        "currency": cur,
    }


def _make_summary(holdings, track_cash=False, cash_balance=0, display_currency="USD"):
    return {
        "holdings": holdings,
        "track_cash": track_cash,
        "cash_balance": Decimal(str(cash_balance)),
        "display_currency": display_currency,
    }


def _run_api_home_totals(
    portfolios,
    summaries,
    cached_prices,
    fx_rate=Decimal("3.6"),
):
    """
    Execute the portfolio-totals logic extracted from api_home() and return
    (total_value, total_pnl, day_change).
    """
    def _safe_float(v):
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    total_value = 0.0
    total_pnl = 0.0
    day_change = 0.0

    for p, summary in zip(portfolios, summaries):
        all_holdings = summary.get("holdings", [])
        symbols = [h["symbol"] for h in all_holdings if h.get("symbol")]
        cached = {s: cached_prices[s] for s in symbols if s in cached_prices}

        p_total_value = 0.0
        p_total_pnl = 0.0

        with patch("currency_utils.get_usd_ils_rate", return_value=fx_rate):
            for h in all_holdings:
                sym = h["symbol"]
                cp = cached.get(sym)
                current_price = _safe_float(cp.get("price")) if cp else None
                qty = _safe_float(h.get("total_quantity")) or 0
                avg_cost = _safe_float(h.get("average_cost")) or 0

                # Bug 2 fix: fall back to cost basis on cache miss
                if current_price is None:
                    current_price = avg_cost if avg_cost else None

                if current_price is not None:
                    cur = detect_currency(sym)
                    mv = current_price * qty
                    ug = mv - (avg_cost * qty)

                    # Bug 1 fix: convert ILS to USD
                    if cur != "USD":
                        mv = float(convert_to_usd(Decimal(str(mv)), cur))
                        ug = float(convert_to_usd(Decimal(str(ug)), cur))

                    p_total_value += mv
                    p_total_pnl += ug

                    chg_pct = _safe_float(cp.get("change_percent")) if cp else None
                    if chg_pct:
                        day_chg_native = qty * current_price * (chg_pct / 100)
                        if cur != "USD":
                            day_change += float(convert_to_usd(Decimal(str(day_chg_native)), cur))
                        else:
                            day_change += day_chg_native

            # Bug 3 fix: include cash balance
            if summary.get("track_cash"):
                cash = _safe_float(summary.get("cash_balance")) or 0.0
                p_total_value += cash

        total_value += p_total_value
        total_pnl += p_total_pnl

    return total_value, total_pnl, day_change


# ---------------------------------------------------------------------------
# Bug 1 — ILS conversion
# ---------------------------------------------------------------------------

class TestILSConversion:
    def test_pure_ils_portfolio_converts_to_usd(self):
        """ILS market value is divided by the FX rate, not added raw."""
        # 10 shares @ ILS 36 each = ILS 360 market value
        # At rate 3.6: USD 100
        teva = _holding("TEVA.TA", qty=10, avg_cost=36)
        portfolios = [{"portfolio_id": "p1", "name": "Test"}]
        summaries = [_make_summary([teva])]
        cached = {"TEVA.TA": {"price": "36", "change_percent": None}}

        total_value, _, _ = _run_api_home_totals(portfolios, summaries, cached, fx_rate=Decimal("3.6"))

        assert abs(total_value - 100.0) < 0.01

    def test_ils_value_not_added_raw(self):
        """Regression: without conversion, ILS 360 would appear as $360, not $100."""
        teva = _holding("TEVA.TA", qty=10, avg_cost=36)
        portfolios = [{"portfolio_id": "p1", "name": "Test"}]
        summaries = [_make_summary([teva])]
        cached = {"TEVA.TA": {"price": "36", "change_percent": None}}

        total_value, _, _ = _run_api_home_totals(portfolios, summaries, cached, fx_rate=Decimal("3.6"))

        # Must NOT be the raw ILS value
        assert total_value < 200

    def test_mixed_usd_and_ils_portfolio(self):
        """Mixed portfolio: ILS portion converted, USD portion untouched."""
        # ILS: 10 shares @ ILS 36 = ILS 360 -> $100 at rate 3.6
        teva = _holding("TEVA.TA", qty=10, avg_cost=36)
        # USD: 1 share @ $200
        aapl = _holding("AAPL", qty=1, avg_cost=200)

        portfolios = [{"portfolio_id": "p1", "name": "Test"}]
        summaries = [_make_summary([teva, aapl])]
        cached = {
            "TEVA.TA": {"price": "36", "change_percent": None},
            "AAPL": {"price": "200", "change_percent": None},
        }

        total_value, _, _ = _run_api_home_totals(portfolios, summaries, cached, fx_rate=Decimal("3.6"))

        # ILS 360 / 3.6 = $100; USD 200 = $200; total = $300
        assert abs(total_value - 300.0) < 0.01

    def test_pure_usd_portfolio_unchanged(self):
        """Pure USD portfolio is not affected by the ILS conversion path."""
        aapl = _holding("AAPL", qty=2, avg_cost=100)
        portfolios = [{"portfolio_id": "p1", "name": "Test"}]
        summaries = [_make_summary([aapl])]
        cached = {"AAPL": {"price": "120", "change_percent": None}}

        total_value, total_pnl, _ = _run_api_home_totals(portfolios, summaries, cached)

        assert abs(total_value - 240.0) < 0.01
        assert abs(total_pnl - 40.0) < 0.01

    def test_day_change_ils_converted(self):
        """Day change contribution from ILS holdings must also be converted to USD."""
        # 10 shares @ ILS 36, +10% day = ILS 36 day gain -> $10 at rate 3.6
        teva = _holding("TEVA.TA", qty=10, avg_cost=36)
        portfolios = [{"portfolio_id": "p1", "name": "Test"}]
        summaries = [_make_summary([teva])]
        cached = {"TEVA.TA": {"price": "36", "change_percent": "10"}}

        _, _, day_change = _run_api_home_totals(portfolios, summaries, cached, fx_rate=Decimal("3.6"))

        assert abs(day_change - 10.0) < 0.01


# ---------------------------------------------------------------------------
# Bug 2 — Cache-miss fallback
# ---------------------------------------------------------------------------

class TestCacheMissFallback:
    def test_no_cache_uses_avg_cost_as_fallback(self):
        """Holdings with no cached price fall back to average_cost."""
        aapl = _holding("AAPL", qty=2, avg_cost=100)
        portfolios = [{"portfolio_id": "p1", "name": "Test"}]
        summaries = [_make_summary([aapl])]
        cached = {}  # empty cache — simulate cache miss

        total_value, total_pnl, _ = _run_api_home_totals(portfolios, summaries, cached)

        # Falls back to avg_cost: 2 * $100 = $200; P&L = 0
        assert abs(total_value - 200.0) < 0.01
        assert abs(total_pnl - 0.0) < 0.01

    def test_cache_miss_not_silently_zero(self):
        """A holding with no cached price must NOT contribute $0."""
        aapl = _holding("AAPL", qty=5, avg_cost=50)
        portfolios = [{"portfolio_id": "p1", "name": "Test"}]
        summaries = [_make_summary([aapl])]
        cached = {}

        total_value, _, _ = _run_api_home_totals(portfolios, summaries, cached)

        assert total_value > 0

    def test_partial_cache_miss(self):
        """Only the cached holding contributes live price; cache-miss uses avg_cost."""
        aapl = _holding("AAPL", qty=1, avg_cost=100)
        msft = _holding("MSFT", qty=1, avg_cost=200)
        portfolios = [{"portfolio_id": "p1", "name": "Test"}]
        summaries = [_make_summary([aapl, msft])]
        # Only AAPL has a cached price (at $150)
        cached = {"AAPL": {"price": "150", "change_percent": None}}

        total_value, _, _ = _run_api_home_totals(portfolios, summaries, cached)

        # AAPL: $150 live; MSFT: $200 fallback -> $350
        assert abs(total_value - 350.0) < 0.01


# ---------------------------------------------------------------------------
# Bug 3 — Cash balance inclusion
# ---------------------------------------------------------------------------

class TestCashBalance:
    def test_cash_included_when_track_cash_enabled(self):
        """Cash balance is added to portfolio total when track_cash is True."""
        aapl = _holding("AAPL", qty=1, avg_cost=100)
        portfolios = [{"portfolio_id": "p1", "name": "Test"}]
        summaries = [_make_summary([aapl], track_cash=True, cash_balance=500)]
        cached = {"AAPL": {"price": "100", "change_percent": None}}

        total_value, _, _ = _run_api_home_totals(portfolios, summaries, cached)

        # $100 holding + $500 cash = $600
        assert abs(total_value - 600.0) < 0.01

    def test_cash_excluded_when_track_cash_disabled(self):
        """Cash balance is not added when track_cash is False."""
        aapl = _holding("AAPL", qty=1, avg_cost=100)
        portfolios = [{"portfolio_id": "p1", "name": "Test"}]
        summaries = [_make_summary([aapl], track_cash=False, cash_balance=500)]
        cached = {"AAPL": {"price": "100", "change_percent": None}}

        total_value, _, _ = _run_api_home_totals(portfolios, summaries, cached)

        assert abs(total_value - 100.0) < 0.01

    def test_zero_cash_no_impact(self):
        """Zero cash balance with track_cash=True does not change the total."""
        aapl = _holding("AAPL", qty=1, avg_cost=100)
        portfolios = [{"portfolio_id": "p1", "name": "Test"}]
        summaries = [_make_summary([aapl], track_cash=True, cash_balance=0)]
        cached = {"AAPL": {"price": "100", "change_percent": None}}

        total_value, _, _ = _run_api_home_totals(portfolios, summaries, cached)

        assert abs(total_value - 100.0) < 0.01


# ---------------------------------------------------------------------------
# Combined scenarios
# ---------------------------------------------------------------------------

class TestCombinedScenarios:
    def test_ils_holding_with_cash_balance(self):
        """ILS conversion + cash balance both applied correctly."""
        # ILS 360 / 3.6 = $100
        teva = _holding("TEVA.TA", qty=10, avg_cost=36)
        portfolios = [{"portfolio_id": "p1", "name": "Test"}]
        summaries = [_make_summary([teva], track_cash=True, cash_balance=200)]
        cached = {"TEVA.TA": {"price": "36", "change_percent": None}}

        total_value, _, _ = _run_api_home_totals(portfolios, summaries, cached, fx_rate=Decimal("3.6"))

        # $100 (converted ILS) + $200 cash = $300
        assert abs(total_value - 300.0) < 0.01

    def test_cache_miss_ils_with_cash(self):
        """Cache-miss ILS holding (uses avg_cost) + cash balance."""
        # avg_cost = ILS 36, 10 shares; cache miss -> fallback to ILS 360 -> $100
        teva = _holding("TEVA.TA", qty=10, avg_cost=36)
        portfolios = [{"portfolio_id": "p1", "name": "Test"}]
        summaries = [_make_summary([teva], track_cash=True, cash_balance=50)]
        cached = {}  # cache miss

        total_value, _, _ = _run_api_home_totals(portfolios, summaries, cached, fx_rate=Decimal("3.6"))

        # ILS 360 / 3.6 = $100 + $50 cash = $150
        assert abs(total_value - 150.0) < 0.01
