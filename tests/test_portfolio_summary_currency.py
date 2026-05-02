"""
Tests for portfolio summary currency handling.

Phase 2: cost basis must be converted to USD before summing so that
total_unrealized_gain is meaningful for portfolios containing TASE (.TA)
holdings whose cost basis is denominated in ILS.
"""

import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from portfolio.portfolio_service import PortfolioService  # noqa: E402


def _holding(symbol, qty, avg_cost, current_price, asset_type="stock", currency=None):
    qty_d = Decimal(str(qty))
    avg_d = Decimal(str(avg_cost))
    return {
        "symbol": symbol,
        "asset_type": asset_type,
        "total_quantity": qty_d,
        "average_cost": avg_d,
        "total_cost_basis": qty_d * avg_d,
        "current_price": Decimal(str(current_price)),
        "price_available": True,
        "market_value": qty_d * Decimal(str(current_price)),
        "unrealized_gain": Decimal("0"),
        "unrealized_gain_pct": Decimal("0"),
        "currency": currency or ("ILS" if symbol.upper().endswith(".TA") else "USD"),
    }


def _make_service_with_holdings(holdings, track_cash=False, cash_balance=0):
    db = MagicMock()
    db.get_portfolio.return_value = {
        "portfolio_id": "p1",
        "track_cash": track_cash,
        "cash_balance": Decimal(str(cash_balance)),
    }
    svc = PortfolioService()
    svc._db = db
    svc.get_holdings = MagicMock(return_value=holdings)
    return svc


def test_mixed_ils_and_usd_cost_basis_converted_to_usd():
    """A holding with ILS cost basis should not pollute USD totals."""
    # 100 shares @ 10 ILS = 1000 ILS cost; price 12 ILS -> 1200 ILS market value
    teva = _holding("TEVA.TA", 100, 10, 12)
    # 1 share @ $100 cost; price $110
    aapl = _holding("AAPL", 1, 100, 110)

    svc = _make_service_with_holdings([teva, aapl])

    # Force a deterministic FX rate so the test isn't network-dependent
    with patch("currency_utils.get_usd_ils_rate", return_value=Decimal("4")):
        summary = svc.get_portfolio_summary("p1", with_prices=True)

    # Cost: 1000 ILS / 4 = 250 USD; plus 100 USD = 350 USD
    assert summary["total_cost_basis"] == Decimal("350")
    # MV: 1200 ILS / 4 = 300 USD; plus 110 USD = 410 USD
    assert summary["total_market_value"] == Decimal("410")
    # Gain = 60 USD
    assert summary["total_unrealized_gain"] == Decimal("60")


def test_all_usd_portfolio_unchanged():
    aapl = _holding("AAPL", 2, 100, 120)
    svc = _make_service_with_holdings([aapl])
    summary = svc.get_portfolio_summary("p1", with_prices=True)

    assert summary["total_cost_basis"] == Decimal("200")
    assert summary["total_market_value"] == Decimal("240")
    assert summary["total_unrealized_gain"] == Decimal("40")
    assert summary["display_currency"] == "USD"


def test_all_ils_portfolio_displays_in_ils():
    teva = _holding("TEVA.TA", 100, 10, 12)
    icl = _holding("ICL.TA", 50, 20, 22)
    svc = _make_service_with_holdings([teva, icl])

    # FX rate should be irrelevant when display currency is ILS
    with patch("currency_utils.get_usd_ils_rate", return_value=Decimal("4")):
        summary = svc.get_portfolio_summary("p1", with_prices=True)

    assert summary["display_currency"] == "ILS"
    assert summary["total_cost_basis"] == Decimal("2000")
    assert summary["total_market_value"] == Decimal("2300")
    assert summary["total_unrealized_gain"] == Decimal("300")


def test_mixed_portfolio_falls_back_to_usd():
    teva = _holding("TEVA.TA", 100, 10, 12)
    aapl = _holding("AAPL", 1, 100, 110)
    svc = _make_service_with_holdings([teva, aapl])

    with patch("currency_utils.get_usd_ils_rate", return_value=Decimal("4")):
        summary = svc.get_portfolio_summary("p1", with_prices=True)

    assert summary["display_currency"] == "USD"


def test_all_ils_with_cash_falls_back_to_usd():
    """Cash is USD-only for now, so any portfolio with track_cash falls back."""
    teva = _holding("TEVA.TA", 100, 10, 12)
    svc = _make_service_with_holdings(
        [teva], track_cash=True, cash_balance=500
    )
    with patch("currency_utils.get_usd_ils_rate", return_value=Decimal("4")):
        summary = svc.get_portfolio_summary("p1", with_prices=True)
    assert summary["display_currency"] == "USD"
