"""
Tests for price cache behavior in portfolio_service.get_holdings().

Production uses PriceCacheService: missing symbols refresh synchronously; stale rows
trigger a background refresh (Thread patched to run inline here). The HTTP response
still shows cached values for stale rows; refresh updates DB for the next request.
"""

import sys
import threading
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

# pytest.ini sets pythonpath = src; keep a fallback for direct runs
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))


def make_holding(symbol, asset_type="stock"):
    return {
        "symbol": symbol,
        "asset_type": asset_type,
        "total_quantity": Decimal("10"),
        "total_cost_basis": Decimal("1000"),
        "average_cost": Decimal("100"),
    }


def make_cache_row(symbol, price, age_minutes=0):
    return {
        "symbol": symbol,
        "price": float(price),
        "change_percent": 1.5,
        "asset_type": "stock",
        "display_name": None,
        "last_updated": datetime.utcnow() - timedelta(minutes=age_minutes),
    }


@pytest.fixture
def service(monkeypatch):
    from portfolio.portfolio_service import PortfolioService
    from price_cache_service import PriceCacheService

    svc = PortfolioService()
    mock_db = MagicMock()
    svc._db = mock_db

    mock_stock_provider = MagicMock()
    mock_crypto_provider = MagicMock()
    mock_factory = MagicMock()
    mock_factory.get_provider.side_effect = (
        lambda t: mock_stock_provider if t == "stock" else mock_crypto_provider
    )
    svc._provider_factory = mock_factory

    svc._mock_db = mock_db
    svc._mock_stock_provider = mock_stock_provider
    svc._mock_crypto_provider = mock_crypto_provider

    real_pcs = PriceCacheService(mock_db, mock_stock_provider, mock_crypto_provider)
    monkeypatch.setattr("price_cache_service._instance", None)
    monkeypatch.setattr("price_cache_service.get_price_cache_service", lambda: real_pcs)

    class ImmediateThread:
        def __init__(
            self,
            group=None,
            target=None,
            name=None,
            args=(),
            kwargs=None,
            *,
            daemon=None,
        ):
            self._target = target
            self._args = args or ()
            self._kwargs = dict(kwargs or {})

        def start(self):
            if self._target:
                self._target(*self._args, **self._kwargs)

    monkeypatch.setattr(threading, "Thread", ImmediateThread)

    return svc


class TestCacheHitSkipsProviders:
    def test_fresh_cache_skips_stock_provider(self, service):
        service._mock_db.get_holdings.return_value = [make_holding("AAPL")]
        service._mock_db.get_cached_prices.return_value = {
            "AAPL": make_cache_row("AAPL", 150.00, age_minutes=5),
        }

        result = service.get_holdings("p-1", with_prices=True)

        service._mock_stock_provider.get_prices_batch_warmup.assert_not_called()
        assert result[0]["current_price"] == Decimal("150.00")

    def test_fresh_cache_skips_crypto_provider(self, service):
        service._mock_db.get_holdings.return_value = [make_holding("BTC", "crypto")]
        row = make_cache_row("BTC", 65000.00, age_minutes=10)
        row["asset_type"] = "crypto"
        service._mock_db.get_cached_prices.return_value = {"BTC": row}

        result = service.get_holdings("p-1", with_prices=True)

        service._mock_crypto_provider.get_prices_with_change.assert_not_called()
        assert result[0]["current_price"] == Decimal("65000.00")


class TestStaleCacheBackgroundRefresh:
    def test_stale_response_still_shows_cached_price_provider_refreshes_db(self, service):
        service._mock_db.get_holdings.return_value = [make_holding("AAPL")]
        service._mock_db.get_cached_prices.return_value = {
            "AAPL": make_cache_row("AAPL", 140.00, age_minutes=20),
        }
        service._mock_stock_provider.get_prices_batch_warmup.return_value = {
            "AAPL": {"price": Decimal("155.00"), "change_percent": None},
        }

        result = service.get_holdings("p-1", with_prices=True)

        service._mock_stock_provider.get_prices_batch_warmup.assert_called_once_with(
            ["AAPL"]
        )
        assert result[0]["current_price"] == Decimal("140.00")
        service._mock_db.upsert_price_cache.assert_called()

    def test_missing_cache_fetches_from_provider_sync(self, service):
        service._mock_db.get_holdings.return_value = [make_holding("TSLA")]
        service._mock_db.get_cached_prices.return_value = {}
        service._mock_stock_provider.get_prices_batch_warmup.return_value = {
            "TSLA": {"price": Decimal("200.00"), "change_percent": None},
        }

        result = service.get_holdings("p-1", with_prices=True)

        service._mock_stock_provider.get_prices_batch_warmup.assert_called_once_with(
            ["TSLA"]
        )
        assert result[0]["current_price"] == Decimal("200.00")

    def test_fetched_price_is_upserted_to_cache(self, service):
        service._mock_db.get_holdings.return_value = [make_holding("AAPL")]
        service._mock_db.get_cached_prices.return_value = {}
        service._mock_stock_provider.get_prices_batch_warmup.return_value = {
            "AAPL": {"price": Decimal("160.00"), "change_percent": None},
        }

        service.get_holdings("p-1", with_prices=True)

        service._mock_db.upsert_price_cache.assert_called_once()
        args = service._mock_db.upsert_price_cache.call_args[0]
        assert args[0] == "AAPL"
        assert args[1] == "stock"
        assert Decimal(str(args[2])) == Decimal("160.00")


class TestPartialCacheHit:
    def test_only_missing_symbols_sent_to_provider(self, service):
        service._mock_db.get_holdings.return_value = [
            make_holding("AAPL"),
            make_holding("TSLA"),
        ]
        service._mock_db.get_cached_prices.return_value = {
            "AAPL": make_cache_row("AAPL", 150.00, age_minutes=5),
        }
        service._mock_stock_provider.get_prices_batch_warmup.return_value = {
            "TSLA": {"price": Decimal("210.00"), "change_percent": None},
        }

        result = service.get_holdings("p-1", with_prices=True)

        service._mock_stock_provider.get_prices_batch_warmup.assert_called_once_with(
            ["TSLA"]
        )

        aapl = next(h for h in result if h["symbol"] == "AAPL")
        tsla = next(h for h in result if h["symbol"] == "TSLA")
        assert aapl["current_price"] == Decimal("150.00")
        assert tsla["current_price"] == Decimal("210.00")


class TestNoPricesNoProviderCall:
    def test_no_provider_call_when_with_prices_false(self, service):
        service._mock_db.get_holdings.return_value = [make_holding("AAPL")]

        result = service.get_holdings("p-1", with_prices=False)

        service._mock_db.get_cached_prices.assert_not_called()
        service._mock_stock_provider.get_prices_batch_warmup.assert_not_called()
        assert result[0]["price_available"] is False


class TestCacheTTL:
    def test_exactly_15_min_triggers_background_refresh(self, service):
        service._mock_db.get_holdings.return_value = [make_holding("AAPL")]
        service._mock_db.get_cached_prices.return_value = {
            "AAPL": make_cache_row("AAPL", 140.00, age_minutes=15),
        }
        service._mock_stock_provider.get_prices_batch_warmup.return_value = {}

        service.get_holdings("p-1", with_prices=True)

        service._mock_stock_provider.get_prices_batch_warmup.assert_called_once()

    def test_just_under_15_min_is_fresh(self, service):
        service._mock_db.get_holdings.return_value = [make_holding("AAPL")]
        row = make_cache_row("AAPL", 150.00, age_minutes=0)
        row["last_updated"] = datetime.utcnow() - timedelta(minutes=14, seconds=59)
        service._mock_db.get_cached_prices.return_value = {"AAPL": row}

        service.get_holdings("p-1", with_prices=True)

        service._mock_stock_provider.get_prices_batch_warmup.assert_not_called()
