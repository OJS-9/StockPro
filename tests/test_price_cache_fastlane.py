"""
Tests for price_cache fastlane in portfolio_service.get_holdings().
Verifies cache-first flow: fresh cache hits skip providers, stale/missing hit providers,
and freshly fetched prices are upserted back into the cache.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from decimal import Decimal
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent / 'src'))


def make_holding(symbol, asset_type='stock'):
    return {
        'symbol': symbol,
        'asset_type': asset_type,
        'total_quantity': Decimal('10'),
        'total_cost_basis': Decimal('1000'),
        'average_cost': Decimal('100'),
    }


def make_cache_row(symbol, price, age_minutes=0):
    """Return a price_cache row dict with last_updated set to age_minutes ago."""
    return {
        'symbol': symbol,
        'price': float(price),
        'change_percent': 1.5,
        'asset_type': 'stock',
        'display_name': None,
        'last_updated': datetime.utcnow() - timedelta(minutes=age_minutes),
    }


@pytest.fixture
def service():
    """PortfolioService with all external deps mocked."""
    from portfolio.portfolio_service import PortfolioService
    svc = PortfolioService()

    # Mock database
    mock_db = MagicMock()
    svc._db = mock_db

    # Mock provider factory + providers
    mock_stock_provider = MagicMock()
    mock_crypto_provider = MagicMock()
    mock_factory = MagicMock()
    mock_factory.get_provider.side_effect = lambda t: mock_stock_provider if t == 'stock' else mock_crypto_provider
    svc._provider_factory = mock_factory

    svc._mock_db = mock_db
    svc._mock_stock_provider = mock_stock_provider
    svc._mock_crypto_provider = mock_crypto_provider

    return svc


class TestCacheHitSkipsProviders:
    """When all symbols are fresh in cache, providers are never called."""

    def test_fresh_cache_skips_stock_provider(self, service):
        service._mock_db.get_holdings.return_value = [make_holding('AAPL')]
        service._mock_db.get_cached_prices.return_value = {
            'AAPL': make_cache_row('AAPL', 150.00, age_minutes=5),  # fresh (< 15 min)
        }

        result = service.get_holdings('p-1', with_prices=True)

        service._mock_stock_provider.get_prices_batch.assert_not_called()
        assert result[0]['current_price'] == Decimal('150.00')

    def test_fresh_cache_skips_crypto_provider(self, service):
        service._mock_db.get_holdings.return_value = [make_holding('BTC', 'crypto')]
        service._mock_db.get_cached_prices.return_value = {
            'BTC': make_cache_row('BTC', 65000.00, age_minutes=10),
        }

        result = service.get_holdings('p-1', with_prices=True)

        service._mock_crypto_provider.get_prices_batch.assert_not_called()
        assert result[0]['current_price'] == Decimal('65000.00')


class TestStaleCacheHitsProviders:
    """When cache is stale or missing, providers are called and cache is upserted."""

    def test_stale_cache_fetches_from_provider(self, service):
        service._mock_db.get_holdings.return_value = [make_holding('AAPL')]
        service._mock_db.get_cached_prices.return_value = {
            'AAPL': make_cache_row('AAPL', 140.00, age_minutes=20),  # stale (> 15 min)
        }
        service._mock_stock_provider.get_prices_batch.return_value = {
            'AAPL': Decimal('155.00')
        }
        service._mock_stock_provider.get_change_percent = MagicMock(return_value=None)

        result = service.get_holdings('p-1', with_prices=True)

        service._mock_stock_provider.get_prices_batch.assert_called_once_with(['AAPL'])
        assert result[0]['current_price'] == Decimal('155.00')

    def test_missing_cache_fetches_from_provider(self, service):
        service._mock_db.get_holdings.return_value = [make_holding('TSLA')]
        service._mock_db.get_cached_prices.return_value = {}  # no cache at all
        service._mock_stock_provider.get_prices_batch.return_value = {
            'TSLA': Decimal('200.00')
        }

        result = service.get_holdings('p-1', with_prices=True)

        service._mock_stock_provider.get_prices_batch.assert_called_once_with(['TSLA'])
        assert result[0]['current_price'] == Decimal('200.00')

    def test_fetched_price_is_upserted_to_cache(self, service):
        service._mock_db.get_holdings.return_value = [make_holding('AAPL')]
        service._mock_db.get_cached_prices.return_value = {}
        service._mock_stock_provider.get_prices_batch.return_value = {
            'AAPL': Decimal('160.00')
        }

        service.get_holdings('p-1', with_prices=True)

        service._mock_db.upsert_price_cache.assert_called_once()
        args = service._mock_db.upsert_price_cache.call_args[0]
        assert args[0] == 'AAPL'
        assert args[1] == 'stock'
        assert Decimal(str(args[2])) == Decimal('160.00')


class TestPartialCacheHit:
    """When some symbols are fresh and some are stale/missing."""

    def test_only_stale_symbols_sent_to_provider(self, service):
        service._mock_db.get_holdings.return_value = [
            make_holding('AAPL'),
            make_holding('TSLA'),
        ]
        service._mock_db.get_cached_prices.return_value = {
            'AAPL': make_cache_row('AAPL', 150.00, age_minutes=5),   # fresh
            # TSLA missing from cache
        }
        service._mock_stock_provider.get_prices_batch.return_value = {
            'TSLA': Decimal('210.00')
        }

        result = service.get_holdings('p-1', with_prices=True)

        # Provider called only for TSLA
        service._mock_stock_provider.get_prices_batch.assert_called_once_with(['TSLA'])

        aapl = next(h for h in result if h['symbol'] == 'AAPL')
        tsla = next(h for h in result if h['symbol'] == 'TSLA')
        assert aapl['current_price'] == Decimal('150.00')
        assert tsla['current_price'] == Decimal('210.00')


class TestNoPricesNoProviderCall:
    """When with_prices=False, cache and providers are never touched."""

    def test_no_provider_call_when_with_prices_false(self, service):
        service._mock_db.get_holdings.return_value = [make_holding('AAPL')]

        result = service.get_holdings('p-1', with_prices=False)

        service._mock_db.get_cached_prices.assert_not_called()
        service._mock_stock_provider.get_prices_batch.assert_not_called()
        assert result[0]['price_available'] is False


class TestCacheTTL:
    """TTL boundary: exactly 15 min is stale; 14 min 59 sec is fresh."""

    def test_exactly_15_min_is_stale(self, service):
        service._mock_db.get_holdings.return_value = [make_holding('AAPL')]
        service._mock_db.get_cached_prices.return_value = {
            'AAPL': make_cache_row('AAPL', 140.00, age_minutes=15),
        }
        service._mock_stock_provider.get_prices_batch.return_value = {}

        service.get_holdings('p-1', with_prices=True)

        service._mock_stock_provider.get_prices_batch.assert_called_once()

    def test_just_under_15_min_is_fresh(self, service):
        service._mock_db.get_holdings.return_value = [make_holding('AAPL')]
        row = make_cache_row('AAPL', 150.00, age_minutes=0)
        row['last_updated'] = datetime.utcnow() - timedelta(minutes=14, seconds=59)
        service._mock_db.get_cached_prices.return_value = {'AAPL': row}

        service.get_holdings('p-1', with_prices=True)

        service._mock_stock_provider.get_prices_batch.assert_not_called()
