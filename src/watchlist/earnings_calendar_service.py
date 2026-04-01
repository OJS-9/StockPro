"""
Watchlist earnings calendar helper.
"""

from datetime import date, timedelta
from typing import Dict, Iterable, List


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


def get_watchlist_earnings_calendar(
    user_id: str, watchlist_id: str, symbols: List[str]
) -> List[Dict[str, str]]:
    """
    Return upcoming earnings events for watchlist symbols.

    If no earnings provider is available, return an empty list rather than raising.
    """
    del user_id, watchlist_id
    tracked = _normalized_symbols(symbols)
    if not tracked:
        return []

    # Provider integration can replace this fallback with real dates.
    next_week = (date.today() + timedelta(days=7)).isoformat()
    return [
        {"symbol": symbol, "report_date": next_week, "time": "TBD", "source": "fallback"}
        for symbol in tracked
    ]
