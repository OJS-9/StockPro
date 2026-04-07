"""
Watchlist earnings calendar helper — uses yfinance for real earnings dates.
"""

import logging
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


def _normalized_symbols(symbols: Iterable[str]) -> List[str]:
    cleaned: List[str] = []
    seen = set()
    for symbol in symbols or []:
        value = (symbol or "").strip().upper()
        if not value or value in seen:
            continue
        seen.add(value)
        cleaned.append(value)
    return cleaned


def _get_earnings_for_symbol(symbol: str) -> Optional[Dict]:
    """Fetch next earnings date from yfinance. Returns None if unavailable."""
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        cal = ticker.calendar
        if cal is None:
            return None

        # yfinance returns calendar as a dict with keys like "Earnings Date", etc.
        earnings_date = None
        if isinstance(cal, dict):
            # Keys vary by yfinance version; try common ones
            for key in ("Earnings Date", "earningsDate", "earnings_date"):
                val = cal.get(key)
                if val is not None:
                    if hasattr(val, "__iter__") and not isinstance(val, str):
                        val = list(val)
                        if val:
                            val = val[0]
                    earnings_date = val
                    break
        elif hasattr(cal, "columns"):
            # DataFrame format (older yfinance)
            try:
                if "Earnings Date" in cal.columns:
                    val = cal["Earnings Date"].iloc[0] if not cal.empty else None
                    earnings_date = val
            except Exception:
                pass

        if earnings_date is None:
            return None

        # Normalize to date string
        if hasattr(earnings_date, "date"):
            earnings_date = earnings_date.date()
        if hasattr(earnings_date, "isoformat"):
            date_str = earnings_date.isoformat()
        else:
            date_str = str(earnings_date)[:10]

        # Only return future earnings (within 90 days)
        try:
            ed = date.fromisoformat(date_str[:10])
            today = date.today()
            if ed < today or ed > today + timedelta(days=90):
                return None
        except Exception:
            return None

        # Try to get EPS estimate
        eps_estimate = None
        if isinstance(cal, dict):
            for key in ("EPS Estimate", "epsEstimate", "eps_estimate"):
                v = cal.get(key)
                if v is not None:
                    try:
                        eps_estimate = float(v)
                    except (TypeError, ValueError):
                        pass
                    break

        return {
            "symbol": symbol,
            "report_date": date_str[:10],
            "time": "TBD",
            "eps_estimate": eps_estimate,
            "source": "yfinance",
        }
    except Exception as e:
        logger.debug("earnings fetch failed for %s: %s", symbol, e)
        return None


def get_watchlist_earnings_calendar(
    user_id: str, watchlist_id: str, symbols: List[str]
) -> List[Dict]:
    """
    Return upcoming earnings events for watchlist symbols.

    Uses yfinance for real data. Returns items sorted by report_date ascending.
    Only includes earnings within the next 90 days.
    """
    del user_id, watchlist_id
    tracked = _normalized_symbols(symbols)
    if not tracked:
        return []

    results = []
    for symbol in tracked:
        item = _get_earnings_for_symbol(symbol)
        if item:
            results.append(item)

    results.sort(key=lambda x: x.get("report_date", ""))
    return results
