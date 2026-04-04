"""
Centralized price cache refresh service.
Single entry point for fetching and caching prices — used by all call sites.
"""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

TTL_MINUTES = 15


class PriceCacheService:

    def __init__(self, db, stock_provider, crypto_provider):
        self.db = db
        self.stock_provider = stock_provider
        self.crypto_provider = crypto_provider

    def refresh(self, symbols, force=False, display_names=None):
        """
        Fetch and upsert prices for the given symbols.

        Args:
            symbols: list of (symbol, asset_type) tuples
            force: skip TTL check and always fetch (use for on-demand/new ticker adds)
            display_names: optional {symbol: display_name} written to cache

        Returns:
            {symbol: {"price": Decimal, "change_percent": Decimal|None}} for fetched symbols only
        """
        if not symbols:
            return {}

        if display_names is None:
            display_names = {}

        if force:
            stale = list(symbols)
        else:
            sym_list = [s for s, _ in symbols]
            cached = self.db.get_cached_prices(sym_list)
            cutoff = datetime.now() - timedelta(minutes=TTL_MINUTES)

            def _is_stale(sym):
                row = cached.get(sym)
                if not row or not row.get("last_updated"):
                    return True
                return row["last_updated"] < cutoff

            stale = [(sym, at) for sym, at in symbols if _is_stale(sym)]

        if not stale:
            return {}

        stocks = [sym for sym, at in stale if at == "stock"]
        cryptos = [sym for sym, at in stale if at == "crypto"]

        result = {}

        if stocks:
            fetched = self.stock_provider.get_prices_batch_warmup(stocks) or {}
            for sym, data in fetched.items():
                price = data.get("price")
                if price is not None:
                    self.db.upsert_price_cache(
                        sym,
                        "stock",
                        float(price),
                        data.get("change_percent"),
                        display_names.get(sym),
                    )
                    result[sym] = {
                        "price": price,
                        "change_percent": data.get("change_percent"),
                    }

        if cryptos:
            fetched = self.crypto_provider.get_prices_with_change(cryptos) or {}
            for sym, data in fetched.items():
                price = data.get("price")
                if price is not None:
                    self.db.upsert_price_cache(
                        sym,
                        "crypto",
                        float(price),
                        data.get("change_percent"),
                        display_names.get(sym),
                    )
                    result[sym] = {
                        "price": price,
                        "change_percent": data.get("change_percent"),
                    }

        return result


_instance = None


def get_price_cache_service():
    global _instance
    if _instance is None:
        from database import get_database_manager
        from data_providers.provider_factory import DataProviderFactory

        _instance = PriceCacheService(
            db=get_database_manager(),
            stock_provider=DataProviderFactory.get_provider("stock"),
            crypto_provider=DataProviderFactory.get_provider("crypto"),
        )
    return _instance
