"""
Background price refresh job — updates price_cache every 15 minutes.
"""

import logging
import sys
import os
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

REFRESH_INTERVAL = 900  # 15 minutes

DEFAULT_SYMBOLS = [
    ("SPY", "stock", "S&P 500"),
    ("BTC", "crypto", "Bitcoin"),
    ("TSLA", "stock", "Tesla Inc."),
]


class PriceRefreshJob:

    def __init__(self):
        self._timer = None
        self._running = False
        self._db = None

    @property
    def db(self):
        if self._db is None:
            from database import get_database_manager

            self._db = get_database_manager()
        return self._db

    def start(self):
        self._running = True
        t = threading.Thread(target=self._run_refresh, daemon=True)
        t.start()

    def stop(self):
        self._running = False
        if self._timer:
            self._timer.cancel()

    def _schedule_next(self):
        if self._running:
            self._timer = threading.Timer(REFRESH_INTERVAL, self._run_refresh)
            self._timer.daemon = True
            self._timer.start()

    def _run_refresh(self):
        try:
            self._do_refresh()
        except Exception:
            logger.exception("price_refresh cycle failed")
        finally:
            self._schedule_next()

    def _do_refresh(self):
        # Collect all symbols from watchlist + price_cache (portfolio holdings, etc.)
        watched = self.db.get_all_watched_symbols()
        symbol_map = {row["symbol"]: row["asset_type"] for row in watched}
        for sym, row in self.db.get_all_cached_prices().items():
            symbol_map.setdefault(sym, row["asset_type"])
        for sym, asset_type, _ in DEFAULT_SYMBOLS:
            symbol_map.setdefault(sym, asset_type)

        default_names = {sym: name for sym, _, name in DEFAULT_SYMBOLS}
        symbols = list(symbol_map.items())  # [(symbol, asset_type), ...]

        logger.info("Price refresh: %d symbols", len(symbols))

        from price_cache_service import get_price_cache_service
        get_price_cache_service().refresh(symbols, display_names=default_names)


_refresh_job = None


def start_price_refresh():
    global _refresh_job
    if _refresh_job is None:
        _refresh_job = PriceRefreshJob()
        _refresh_job.start()
        logger.info("Background price refresh started")
    return _refresh_job
