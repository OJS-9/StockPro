"""
Watchlist service — CRUD for watchlists, sections, items, and pinned tickers.
"""

import logging
import sys
import os
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

# Defaults shown on homepage when user has fewer than 3 pins
DEFAULT_PINS = [
    {"symbol": "SPY", "asset_type": "stock", "display_name": "S&P 500"},
    {"symbol": "BTC", "asset_type": "crypto", "display_name": "Bitcoin"},
    {"symbol": "TSLA", "asset_type": "stock", "display_name": "Tesla Inc."},
]


class WatchlistService:

    def __init__(self):
        self._db = None
        self._provider_factory = None

    @property
    def db(self):
        if self._db is None:
            from database import get_database_manager

            self._db = get_database_manager()
        return self._db

    @property
    def provider_factory(self):
        if self._provider_factory is None:
            from data_providers.provider_factory import DataProviderFactory

            self._provider_factory = DataProviderFactory
        return self._provider_factory

    # ── Watchlist CRUD ───────────────────────────────────────

    def get_or_create_default_watchlist(self, user_id):
        watchlists = self.db.list_watchlists(user_id)
        if watchlists:
            return watchlists[0]
        watchlist_id = str(uuid4())
        self.db.create_watchlist(watchlist_id, user_id, "My Watchlist")
        return self.db.get_watchlist(watchlist_id)

    def create_watchlist(self, user_id, name):
        watchlist_id = str(uuid4())
        self.db.create_watchlist(watchlist_id, user_id, name)
        return watchlist_id

    def rename_watchlist(self, watchlist_id, name):
        self.db.update_watchlist(watchlist_id, name)

    def delete_watchlist(self, watchlist_id):
        self.db.delete_watchlist(watchlist_id)

    def list_watchlists(self, user_id):
        return self.db.list_watchlists(user_id)

    def get_watchlist_with_items(self, watchlist_id):
        watchlist = self.db.get_watchlist(watchlist_id)
        if not watchlist:
            return None

        items = self.db.get_watchlist_items(watchlist_id)
        sections_list = self.db.list_sections(watchlist_id)

        # Enrich with prices
        symbols = [item["symbol"] for item in items]
        prices = self.db.get_cached_prices(symbols) if symbols else {}

        def enrich(item):
            cache = prices.get(item["symbol"], {})
            item["price"] = cache.get("price")
            item["change_percent"] = cache.get("change_percent")
            item["price_last_updated"] = cache.get("last_updated")
            item["currency"] = cache.get("currency", "USD")
            return item

        items = [enrich(item) for item in items]

        # Group by section
        sections_map = {
            s["section_id"]: dict(s, section_items=[]) for s in sections_list
        }
        unsectioned = []

        for item in items:
            sid = item.get("section_id")
            if sid and sid in sections_map:
                sections_map[sid]["section_items"].append(item)
            else:
                unsectioned.append(item)

        watchlist["sections"] = list(sections_map.values())
        watchlist["unsectioned_items"] = unsectioned
        return watchlist

    # ── Symbols ──────────────────────────────────────────────

    def add_symbol(self, watchlist_id, symbol, section_id=None):
        symbol = symbol.strip().upper()
        asset_type = self.provider_factory.detect_asset_type(symbol)
        display_name = self._fetch_display_name(symbol, asset_type)

        item_id = str(uuid4())
        try:
            self.db.add_watchlist_item(
                item_id, watchlist_id, symbol, asset_type, display_name, section_id
            )
        except Exception as e:
            if "Duplicate entry" in str(e) or "1062" in str(e):
                raise ValueError(f"{symbol} is already in this watchlist")
            raise

        # Immediately fetch price into cache
        self._refresh_symbol_price(symbol, asset_type, display_name)
        return item_id

    def remove_symbol(self, item_id):
        self.db.remove_watchlist_item(item_id)

    def _fetch_display_name(self, symbol, asset_type):
        try:
            provider, _ = self.provider_factory.get_provider_for_symbol(symbol)
            info = provider.get_asset_info(symbol)
            if info:
                return info.get("name") or symbol
        except Exception:
            pass
        return symbol

    def _refresh_symbol_price(self, symbol, asset_type, display_name=None):
        try:
            from price_cache_service import get_price_cache_service

            get_price_cache_service().refresh(
                [(symbol, asset_type)],
                force=True,
                display_names={symbol: display_name} if display_name else None,
            )
        except Exception as e:
            logger.warning("Price fetch failed for %s: %s", symbol, e)

    # ── Sections ─────────────────────────────────────────────

    def create_section(self, watchlist_id, name):
        section_id = str(uuid4())
        self.db.create_section(section_id, watchlist_id, name)
        return section_id

    def rename_section(self, section_id, name):
        self.db.update_section(section_id, name)

    def delete_section(self, section_id):
        self.db.delete_section(section_id)

    def move_item_to_section(self, item_id, section_id):
        self.db.move_item_to_section(item_id, section_id or None)

    # ── Pins ─────────────────────────────────────────────────

    def pin_item(self, user_id, item_id):
        count = self.db.count_pinned_items(user_id)
        if count >= 3:
            raise ValueError("You already have 3 pinned tickers. Unpin one first.")
        self.db.set_item_pinned(item_id, True)

    def unpin_item(self, item_id):
        self.db.set_item_pinned(item_id, False)

    def get_pinned_tickers(self, user_id):
        """Return exactly 3 tickers: user pins + defaults to fill remaining slots."""
        if not user_id:
            return None

        pinned_items = self.db.get_pinned_items(user_id)
        pinned_symbols = {item["symbol"] for item in pinned_items}

        symbols_needed = [item["symbol"] for item in pinned_items]
        # Fill with defaults not already pinned
        for default in DEFAULT_PINS:
            if len(symbols_needed) >= 3:
                break
            if default["symbol"] not in pinned_symbols:
                symbols_needed.append(default["symbol"])

        prices = self.db.get_cached_prices(symbols_needed)

        result = []
        for item in pinned_items:
            sym = item["symbol"]
            cache = prices.get(sym, {})
            result.append(
                {
                    "symbol": sym,
                    "asset_type": item["asset_type"],
                    "display_name": item.get("display_name") or sym,
                    "price": cache.get("price"),
                    "change_percent": cache.get("change_percent"),
                }
            )

        # Add defaults for remaining slots
        for default in DEFAULT_PINS:
            if len(result) >= 3:
                break
            if default["symbol"] not in pinned_symbols:
                sym = default["symbol"]
                cache = prices.get(sym, {})
                result.append(
                    {
                        "symbol": sym,
                        "asset_type": default["asset_type"],
                        "display_name": default["display_name"],
                        "price": cache.get("price"),
                        "change_percent": cache.get("change_percent"),
                    }
                )

        return result[:3]


_watchlist_service = None


def get_watchlist_service():
    global _watchlist_service
    if _watchlist_service is None:
        _watchlist_service = WatchlistService()
    return _watchlist_service
