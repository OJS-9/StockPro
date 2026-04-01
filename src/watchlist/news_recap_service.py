"""
Watchlist news recap helper.
"""

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


def get_watchlist_news_recap(
    user_id: str, watchlist_id: str, symbols: List[str], max_items: int = 12
) -> List[Dict[str, str]]:
    """
    Build a compact watchlist-oriented recap payload.

    This intentionally degrades gracefully when the optional news provider is
    unavailable so the API route can still return a valid response shape.
    """
    del user_id, watchlist_id  # retained for future per-user personalization
    tracked = _normalized_symbols(symbols)
    if not tracked:
        return []

    try:
        from news_service import get_briefing

        articles = get_briefing() or []
    except Exception:
        return []

    digest: List[Dict[str, str]] = []
    for article in articles:
        title = str((article or {}).get("title", "")).strip()
        if not title:
            continue
        upper_title = title.upper()
        matched_symbol = next((s for s in tracked if s in upper_title), None)
        if not matched_symbol:
            continue
        digest.append(
            {
                "symbol": matched_symbol,
                "title": title,
                "summary": str(article.get("description", "")).strip(),
                "source": str(article.get("publisher", "")).strip(),
                "url": str(article.get("url", "")).strip(),
            }
        )
        if len(digest) >= max_items:
            break
    return digest
