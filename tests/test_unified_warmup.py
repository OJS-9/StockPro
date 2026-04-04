"""
Tests for unified price warmup: portfolio + watchlist symbols, DB freshness check,
and concurrent batch fetch in price_refresh.py.
"""
import sys
import os
import unittest
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))


class TestGetWatchedSymbolsForUser(unittest.TestCase):
    """Tests for DatabaseManager.get_watched_symbols_for_user"""

    def _make_db(self):
        """Import and create a DatabaseManager with a mocked psycopg2 pool."""
        from database import DatabaseManager
        db = DatabaseManager.__new__(DatabaseManager)
        db._pool = MagicMock()
        return db

    def test_returns_symbols_for_user(self):
        db = self._make_db()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: mock_cursor
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = [
            {'symbol': 'AAPL', 'asset_type': 'stock'},
            {'symbol': 'BTC', 'asset_type': 'crypto'},
        ]
        mock_conn.cursor.return_value = mock_cursor
        db._pool.getconn.return_value = mock_conn

        result = db.get_watched_symbols_for_user('user_123')

        self.assertEqual(len(result), 2)
        symbols = {r['symbol'] for r in result}
        self.assertIn('AAPL', symbols)
        self.assertIn('BTC', symbols)
        # Verify query uses user_id param
        call_args = mock_cursor.execute.call_args
        self.assertIn('user_id', call_args[0][0].lower())
        db._pool.putconn.assert_called_with(mock_conn)

    def test_returns_empty_list_when_no_watchlist(self):
        db = self._make_db()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = lambda s: mock_cursor
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value = mock_cursor
        db._pool.getconn.return_value = mock_conn

        result = db.get_watched_symbols_for_user('user_no_watchlist')
        self.assertEqual(result, [])


class TestWarmPortfolioCacheFreshnessCheck(unittest.TestCase):
    """Tests that _warm_portfolio_cache skips fresh symbols and fetches stale ones."""

    def _call_warm(self, portfolios, holdings_map, watchlist_rows, cached_prices,
                   stock_prices=None, crypto_prices=None):
        """Helper to call _warm_portfolio_cache with controlled mocks."""
        stock_prices = stock_prices or {}
        crypto_prices = crypto_prices or {}

        mock_db = MagicMock()
        mock_db.get_holdings.side_effect = lambda pid: holdings_map.get(pid, [])
        mock_db.get_watched_symbols_for_user.return_value = watchlist_rows
        mock_db.get_cached_prices.return_value = cached_prices

        mock_svc = MagicMock()
        mock_svc.db = mock_db
        mock_svc.list_portfolios.return_value = portfolios

        mock_stock_provider = MagicMock()
        # Convert flat {sym: price} to new {sym: {'price': ..., 'change_percent': ...}} format
        mock_stock_provider.get_prices_batch_warmup.return_value = {
            sym: {"price": price, "change_percent": None}
            for sym, price in stock_prices.items()
        }
        mock_crypto_provider = MagicMock()
        mock_crypto_provider.get_prices_batch.return_value = crypto_prices

        with patch('app.get_portfolio_service', return_value=mock_svc), \
             patch('app.DataProviderFactory') as mock_factory:
            mock_factory.get_provider.side_effect = lambda t: (
                mock_stock_provider if t == 'stock' else mock_crypto_provider
            )
            from app import _warm_portfolio_cache
            _warm_portfolio_cache('user_1')

        return mock_db, mock_stock_provider, mock_crypto_provider

    def test_skips_fresh_symbols(self):
        """Symbols updated < 15 min ago should not be fetched.
        Uses datetime.now() to match MySQL TIMESTAMP (naive local-server-time)."""
        fresh_time = datetime.now() - timedelta(minutes=5)
        portfolios = [{'portfolio_id': 1}]
        holdings = {'AAPL': 'stock', 'BTC': 'crypto'}
        holdings_map = {1: [
            {'symbol': 'AAPL', 'asset_type': 'stock', 'total_quantity': '10'},
            {'symbol': 'BTC', 'asset_type': 'crypto', 'total_quantity': '1'},
        ]}
        cached = {
            'AAPL': {'symbol': 'AAPL', 'last_updated': fresh_time},
            'BTC': {'symbol': 'BTC', 'last_updated': fresh_time},
        }
        db, stock_prov, crypto_prov = self._call_warm(
            portfolios, holdings_map, [], cached
        )
        stock_prov.get_prices_batch_warmup.assert_not_called()
        crypto_prov.get_prices_batch.assert_not_called()

    def test_fetches_stale_symbols(self):
        """Symbols older than 15 min should be fetched."""
        stale_time = datetime.now() - timedelta(minutes=20)
        portfolios = [{'portfolio_id': 1}]
        holdings_map = {1: [
            {'symbol': 'AAPL', 'asset_type': 'stock', 'total_quantity': '10'},
        ]}
        cached = {
            'AAPL': {'symbol': 'AAPL', 'last_updated': stale_time},
        }
        db, stock_prov, crypto_prov = self._call_warm(
            portfolios, holdings_map, [], cached,
            stock_prices={'AAPL': 175.0}
        )
        stock_prov.get_prices_batch_warmup.assert_called_once_with(['AAPL'])
        db.upsert_price_cache.assert_called_once_with('AAPL', 'stock', 175.0, None, None)  # change_percent from mock is None

    def test_collects_watchlist_symbols(self):
        """Watchlist symbols for the user should be merged into the fetch set."""
        stale_time = datetime.now() - timedelta(minutes=30)
        portfolios = [{'portfolio_id': 1}]
        holdings_map = {1: [
            {'symbol': 'AAPL', 'asset_type': 'stock', 'total_quantity': '5'},
        ]}
        # MSFT is watchlist-only
        watchlist_rows = [{'symbol': 'MSFT', 'asset_type': 'stock'}]
        cached = {
            'AAPL': {'symbol': 'AAPL', 'last_updated': stale_time},
            'MSFT': {'symbol': 'MSFT', 'last_updated': stale_time},
        }
        db, stock_prov, crypto_prov = self._call_warm(
            portfolios, holdings_map, watchlist_rows, cached,
            stock_prices={'AAPL': 175.0, 'MSFT': 420.0}
        )
        call_args = stock_prov.get_prices_batch_warmup.call_args[0][0]
        self.assertIn('AAPL', call_args)
        self.assertIn('MSFT', call_args)

    def test_deduplicates_symbols_across_portfolio_and_watchlist(self):
        """A symbol in both portfolio and watchlist should only be fetched once."""
        stale_time = datetime.now() - timedelta(minutes=25)
        portfolios = [{'portfolio_id': 1}]
        holdings_map = {1: [
            {'symbol': 'AAPL', 'asset_type': 'stock', 'total_quantity': '5'},
        ]}
        # AAPL also in watchlist
        watchlist_rows = [{'symbol': 'AAPL', 'asset_type': 'stock'}]
        cached = {
            'AAPL': {'symbol': 'AAPL', 'last_updated': stale_time},
        }
        db, stock_prov, _ = self._call_warm(
            portfolios, holdings_map, watchlist_rows, cached,
            stock_prices={'AAPL': 175.0}
        )
        call_args = stock_prov.get_prices_batch_warmup.call_args[0][0]
        self.assertEqual(call_args.count('AAPL'), 1)

    def test_symbols_not_in_cache_are_fetched(self):
        """Symbols with no cache entry should be treated as stale."""
        portfolios = [{'portfolio_id': 1}]
        holdings_map = {1: [
            {'symbol': 'NVDA', 'asset_type': 'stock', 'total_quantity': '3'},
        ]}
        cached = {}  # nothing cached
        db, stock_prov, _ = self._call_warm(
            portfolios, holdings_map, [], cached,
            stock_prices={'NVDA': 900.0}
        )
        stock_prov.get_prices_batch_warmup.assert_called_once_with(['NVDA'])

    def test_fresh_symbol_using_local_time_is_skipped(self):
        """Regression: MySQL TIMESTAMP returns naive local-server-time, not UTC.
        A symbol cached 5 min ago (datetime.now()) must be treated as fresh
        even on non-UTC hosts. Using datetime.utcnow() in _is_fresh() would
        compute a ~TZ-offset diff (e.g. 5h on EST), making fresh data look stale.
        This test simulates MySQL returning datetime.now() for last_updated.
        """
        # Simulate MySQL returning local-server-time (datetime.now()), 5 min ago
        local_fresh_time = datetime.now() - timedelta(minutes=5)
        portfolios = [{'portfolio_id': 1}]
        holdings_map = {1: [
            {'symbol': 'AAPL', 'asset_type': 'stock', 'total_quantity': '10'},
        ]}
        cached = {
            'AAPL': {'symbol': 'AAPL', 'last_updated': local_fresh_time},
        }
        db, stock_prov, crypto_prov = self._call_warm(
            portfolios, holdings_map, [], cached
        )
        # Should NOT fetch — data is fresh (only 5 min old)
        stock_prov.get_prices_batch_warmup.assert_not_called()
        crypto_prov.get_prices_batch.assert_not_called()

    def test_stale_symbol_using_local_time_is_fetched(self):
        """Companion to local-time regression: a symbol 20 min old (datetime.now())
        must be treated as stale regardless of timezone."""
        local_stale_time = datetime.now() - timedelta(minutes=20)
        portfolios = [{'portfolio_id': 1}]
        holdings_map = {1: [
            {'symbol': 'TSLA', 'asset_type': 'stock', 'total_quantity': '5'},
        ]}
        cached = {
            'TSLA': {'symbol': 'TSLA', 'last_updated': local_stale_time},
        }
        db, stock_prov, _ = self._call_warm(
            portfolios, holdings_map, [], cached,
            stock_prices={'TSLA': 250.0}
        )
        stock_prov.get_prices_batch_warmup.assert_called_once_with(['TSLA'])


class TestPriceRefreshBatchStock(unittest.TestCase):
    """Tests that _do_refresh uses concurrent batch for stocks (no sleep)."""

    def test_do_refresh_uses_batch_warmup_for_stocks(self):
        """_do_refresh should call get_prices_batch_warmup, not get_price_with_change."""
        from watchlist.price_refresh import PriceRefreshJob

        mock_db = MagicMock()
        mock_db.get_all_watched_symbols.return_value = [
            {'symbol': 'AAPL', 'asset_type': 'stock'},
            {'symbol': 'TSLA', 'asset_type': 'stock'},
        ]
        # All symbols stale (not in cache) so refresh proceeds
        mock_db.get_cached_prices.return_value = {}

        mock_provider = MagicMock()
        mock_provider.get_prices_batch_warmup.return_value = {
            'AAPL': {'price': 175.0, 'change_percent': 1.5},
            'TSLA': {'price': 250.0, 'change_percent': -0.8},
        }

        mock_factory = MagicMock()
        mock_factory.get_provider_for_symbol.return_value = (mock_provider, 'stock')

        job = PriceRefreshJob()
        job._db = mock_db
        job._provider_factory = mock_factory

        job._do_refresh()

        mock_provider.get_prices_batch_warmup.assert_called_once()
        # Must NOT call per-stock sequential method
        mock_provider.get_price_with_change.assert_not_called()

    def test_do_refresh_no_time_sleep(self):
        """No time.sleep calls should remain in _do_refresh for stock fetching."""
        import inspect
        from watchlist import price_refresh
        source = inspect.getsource(price_refresh.PriceRefreshJob._do_refresh)
        self.assertNotIn('time.sleep', source,
                         "_do_refresh should not call time.sleep (removed with STOCK_CALL_DELAY)")

    def test_stock_call_delay_constant_removed(self):
        """STOCK_CALL_DELAY constant should be removed from price_refresh module."""
        from watchlist import price_refresh
        self.assertFalse(
            hasattr(price_refresh, 'STOCK_CALL_DELAY'),
            "STOCK_CALL_DELAY should be removed from price_refresh module"
        )


if __name__ == '__main__':
    unittest.main()
