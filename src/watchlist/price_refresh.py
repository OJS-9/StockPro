"""
Background price refresh job — updates price_cache every 15 minutes.
Respects Alpha Vantage 5 calls/min rate limit by staggering stock fetches.
"""
import sys
import os
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REFRESH_INTERVAL = 900   # 15 minutes
STOCK_CALL_DELAY = 13    # seconds between Alpha Vantage calls (5/min limit)

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
        # Collect all symbols from watchlist + defaults
        watched = self.db.get_all_watched_symbols()
        symbol_map = {row['symbol']: row['asset_type'] for row in watched}

        # Ensure defaults are always refreshed
        for sym, asset_type, display_name in DEFAULT_SYMBOLS:
            symbol_map.setdefault(sym, asset_type)

        # Build display_name map from defaults
        default_names = {sym: name for sym, _, name in DEFAULT_SYMBOLS}

        stocks = [(sym, default_names.get(sym)) for sym, at in symbol_map.items() if at == 'stock']
        cryptos = [(sym, default_names.get(sym)) for sym, at in symbol_map.items() if at == 'crypto']

        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[price_refresh] {ts} Refreshing {len(stocks)} stocks, {len(cryptos)} cryptos")

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

        # Stocks: sequential with delay
        for i, (sym, display_name) in enumerate(stocks):
            try:
                provider, _ = self.provider_factory.get_provider_for_symbol(sym)
                data = provider.get_price_with_change(sym)
                if data.get('price') is not None:
                    self.db.upsert_price_cache(sym, 'stock', data['price'], data.get('change_percent'), display_name)
            except Exception as e:
                print(f"[price_refresh] Stock {sym} error: {e}")
            if i < len(stocks) - 1:
                time.sleep(STOCK_CALL_DELAY)


_refresh_job = None


def start_price_refresh():
    global _refresh_job
    if _refresh_job is None:
        _refresh_job = PriceRefreshJob()
        _refresh_job.start()
        print("[price_refresh] Background price refresh started")
    return _refresh_job
