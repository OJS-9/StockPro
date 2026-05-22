"""
Read-only diagnostic: dump a user's portfolios with raw + currency-aware totals.

Usage:
    python scripts/dump_portfolio.py --user-id user_xxx
    python scripts/dump_portfolio.py --email someone@example.com
"""

import argparse
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv

load_dotenv()

from database import get_database_manager  # noqa: E402
from portfolio.portfolio_service import PortfolioService  # noqa: E402
from currency_utils import detect_currency, convert_to_usd  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--user-id")
    g.add_argument("--email")
    args = parser.parse_args()

    db = get_database_manager()

    if args.email:
        user = db.get_user_by_email(args.email)
        if not user:
            print(f"No user found for email {args.email}")
            sys.exit(1)
        user_id = user["user_id"]
    else:
        user_id = args.user_id

    print(f"\nUser: {user_id}\n")

    portfolios = db.list_portfolios(user_id=user_id)
    if not portfolios:
        print("No portfolios.")
        return

    svc = PortfolioService(db)

    for p in portfolios:
        pid = p["portfolio_id"]
        print(f"=== Portfolio: {p['name']} ({pid}) ===")
        holdings = svc.get_holdings(pid, with_prices=True)

        print(
            f"{'symbol':<12} {'qty':>10} {'avg_cost':>12} "
            f"{'cost_basis':>14} {'cur':>4} {'price':>12}"
        )
        for h in holdings:
            sym = h["symbol"]
            cur = h.get("currency") or detect_currency(sym)
            print(
                f"{sym:<12} "
                f"{str(h.get('total_quantity', '')):>10} "
                f"{str(h.get('average_cost', '')):>12} "
                f"{str(h.get('total_cost_basis', '')):>14} "
                f"{cur:>4} "
                f"{str(h.get('current_price', '')):>12}"
            )

        summary = svc.get_portfolio_summary(pid, with_prices=True)
        print("\n-- API summary (what the SPA sees today) --")
        for k in (
            "total_cost_basis",
            "total_market_value",
            "total_unrealized_gain",
            "total_unrealized_gain_pct",
        ):
            print(f"  {k}: {summary.get(k)}")

        # Manually compute expected USD totals (post-fix expectation)
        expected_cost_usd = Decimal("0")
        expected_mv_usd = Decimal("0")
        for h in holdings:
            cur = h.get("currency") or detect_currency(h["symbol"])
            cb = Decimal(str(h.get("total_cost_basis") or 0))
            expected_cost_usd += convert_to_usd(cb, cur)
            mv = h.get("market_value")
            if mv is not None:
                expected_mv_usd += convert_to_usd(Decimal(str(mv)), cur)

        expected_gain = expected_mv_usd - expected_cost_usd
        expected_gain_pct = (
            (expected_gain / expected_cost_usd) * 100
            if expected_cost_usd > 0
            else Decimal("0")
        )
        print("\n-- Expected (cost basis converted to USD) --")
        print(f"  total_cost_basis (USD): {expected_cost_usd}")
        print(f"  total_market_value (USD): {expected_mv_usd}")
        print(f"  total_unrealized_gain (USD): {expected_gain}")
        print(f"  total_unrealized_gain_pct: {expected_gain_pct}")
        print()


if __name__ == "__main__":
    main()
