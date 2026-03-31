"""
Background price refresh job — updates price_cache every 15 minutes.
Respects Alpha Vantage 5 calls/min rate limit by staggering stock fetches.
"""
import sys
import os
import threading
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REFRESH_INTERVAL = 900   # 15 minutes

DEFAULT_SYMBOLS = [
    ('SPY',  'stock',  'S&P 500'),
    ('BTC',  'crypto', 'Bitcoin'),
    ('TSLA', 'stock',  'Tesla Inc.'),
]


class PriceRefreshJob:

    def __init__(self):
        self._timer = None
        self._running = False
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
        except Exception as e:
            print(f"[price_refresh] Error: {e}")
        finally:
            self._schedule_next()

    def _do_refresh(self):
        # Collect all symbols from watchlist
        watched = self.db.get_all_watched_symbols()
        symbol_map = {row['symbol']: row['asset_type'] for row in watched}

        # Include all symbols already in price_cache (portfolio holdings, etc.)
        for sym, row in self.db.get_all_cached_prices().items():
            symbol_map.setdefault(sym, row['asset_type'])

        # Ensure defaults are always refreshed
        for sym, asset_type, display_name in DEFAULT_SYMBOLS:
            symbol_map.setdefault(sym, asset_type)

        # Build display_name map from defaults
        default_names = {sym: name for sym, _, name in DEFAULT_SYMBOLS}

        stocks = [(sym, default_names.get(sym)) for sym, at in symbol_map.items() if at == 'stock']
        cryptos = [(sym, default_names.get(sym)) for sym, at in symbol_map.items() if at == 'crypto']

        # Skip symbols already fresh in DB (< 15 min old) — single source of truth
        all_syms = [s for s, _ in stocks] + [s for s, _ in cryptos]
        cached = self.db.get_cached_prices(all_syms)
        cutoff = datetime.now() - timedelta(minutes=15)

        def _is_stale(sym):
            row = cached.get(sym)
            if not row or not row.get('last_updated'):
                return True
            return row['last_updated'] < cutoff

        stocks  = [(s, n) for s, n in stocks  if _is_stale(s)]
        cryptos = [(s, n) for s, n in cryptos if _is_stale(s)]

        print(f"[price_refresh] Refreshing {len(stocks)} stocks, {len(cryptos)} cryptos")

        # Crypto: batch fetch with change%
        if cryptos:
            try:
                crypto_symbols = [s for s, _ in cryptos]
                crypto_names = {s: n for s, n in cryptos}
                provider, _ = self.provider_factory.get_provider_for_symbol('BTC')
                batch = provider.get_prices_with_change(crypto_symbols)
                for sym, data in batch.items():
                    self.db.upsert_price_cache(
                        sym, 'crypto',
                        data.get('price'), data.get('change_percent'),
                        crypto_names.get(sym)
                    )
            except Exception as e:
                print(f"[price_refresh] Crypto batch error: {e}")

        # Concurrent batch fetch for stocks
        if stocks:
            stock_symbols = [s for s, _ in stocks]
            stock_names   = {s: n for s, n in stocks}
            provider, _   = self.provider_factory.get_provider_for_symbol('AAPL')
            prices        = provider.get_prices_batch_warmup(stock_symbols)
            for sym, data in prices.items():
                self.db.upsert_price_cache(
                    sym, 'stock',
                    float(data["price"]),
                    data.get("change_percent"),
                    stock_names.get(sym),
                )


_refresh_job = None


def start_price_refresh():
    global _refresh_job
    if _refresh_job is None:
        _refresh_job = PriceRefreshJob()
        _refresh_job.start()
        print("[price_refresh] Background price refresh started")
    return _refresh_job
