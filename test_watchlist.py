"""
Tests for watchlist service — WatchlistService unit tests using mocked DB and provider factory.
"""

import sys
import os
from unittest.mock import MagicMock, patch, call
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from watchlist.watchlist_service import WatchlistService, DEFAULT_PINS, get_watchlist_service


class TestWatchlistService:

    def setup_method(self):
        self.service = WatchlistService()
        # Mock the db and provider_factory lazily
        self.mock_db = MagicMock()
        self.mock_factory = MagicMock()
        self.service._db = self.mock_db
        self.service._provider_factory = self.mock_factory

    # ── Watchlist CRUD ───────────────────────────────────────

    def test_get_or_create_creates_default_when_none_exist(self):
        self.mock_db.list_watchlists.return_value = []
        self.mock_db.get_watchlist.return_value = {
            'watchlist_id': 'wl-1', 'user_id': 'u-1', 'name': 'My Watchlist'
        }

        result = self.service.get_or_create_default_watchlist('u-1')

        assert self.mock_db.create_watchlist.called
        args = self.mock_db.create_watchlist.call_args[0]
        assert args[1] == 'u-1'
        assert args[2] == 'My Watchlist'
        assert result['watchlist_id'] == 'wl-1'

    def test_get_or_create_returns_first_if_exists(self):
        existing = {'watchlist_id': 'wl-existing', 'user_id': 'u-1', 'name': 'My Watchlist'}
        self.mock_db.list_watchlists.return_value = [existing]

        result = self.service.get_or_create_default_watchlist('u-1')

        assert not self.mock_db.create_watchlist.called
        assert result == existing

    def test_list_watchlists(self):
        self.mock_db.list_watchlists.return_value = [
            {'watchlist_id': 'wl-1', 'name': 'Main'},
        ]
        result = self.service.list_watchlists('u-1')
        assert len(result) == 1
        assert result[0]['name'] == 'Main'

    # ── Add symbol ───────────────────────────────────────────

    def test_add_symbol_normalizes_to_uppercase(self):
        self.mock_factory.detect_asset_type.return_value = 'stock'
        mock_provider = MagicMock()
        mock_provider.get_asset_info.return_value = {'name': 'Apple Inc.'}
        mock_provider.get_current_price.return_value = Decimal('190.00')
        self.mock_factory.get_provider_for_symbol.return_value = (mock_provider, 'stock')

        self.service.add_symbol('wl-1', 'aapl')

        args = self.mock_db.add_watchlist_item.call_args[0]
        assert args[2] == 'AAPL'  # symbol is uppercase

    def test_add_symbol_raises_on_duplicate(self):
        self.mock_factory.detect_asset_type.return_value = 'stock'
        mock_provider = MagicMock()
        mock_provider.get_asset_info.return_value = None
        mock_provider.get_current_price.return_value = None
        self.mock_factory.get_provider_for_symbol.return_value = (mock_provider, 'stock')
        self.mock_db.add_watchlist_item.side_effect = Exception('duplicate key value violates unique constraint "watchlist_items_watchlist_id_symbol_key"')

        try:
            self.service.add_symbol('wl-1', 'AAPL')
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert 'already in this watchlist' in str(e)

    def test_add_symbol_fetches_price_immediately(self):
        self.mock_factory.detect_asset_type.return_value = 'crypto'
        mock_provider = MagicMock()
        mock_provider.get_asset_info.return_value = {'name': 'Bitcoin'}
        mock_provider.get_current_price.return_value = Decimal('60000')
        mock_provider.get_prices_with_change.return_value = {
            'BTC': {'price': Decimal('60000'), 'change_percent': Decimal('2.5')}
        }
        self.mock_factory.get_provider_for_symbol.return_value = (mock_provider, 'crypto')

        self.service.add_symbol('wl-1', 'BTC')

        assert self.mock_db.upsert_price_cache.called
        call_args = self.mock_db.upsert_price_cache.call_args[0]
        assert call_args[0] == 'BTC'
        assert call_args[1] == 'crypto'

    # ── Pins ─────────────────────────────────────────────────

    def test_get_pinned_tickers_returns_none_for_guest(self):
        result = self.service.get_pinned_tickers(None)
        assert result is None

    def test_get_pinned_tickers_returns_exactly_3(self):
        # User has 1 pin (AAPL), defaults (SPY, BTC, TSLA) fill remaining 2 slots
        self.mock_db.get_pinned_items.return_value = [
            {'symbol': 'AAPL', 'asset_type': 'stock', 'display_name': 'Apple Inc.', 'watchlist_id': 'wl-1', 'item_id': 'i-1'}
        ]
        prices = {
            'AAPL': {'price': Decimal('190'), 'change_percent': Decimal('1.2')},
            'SPY': {'price': Decimal('500'), 'change_percent': Decimal('0.5')},
            'BTC': {'price': Decimal('60000'), 'change_percent': Decimal('2.0')},
        }
        self.mock_db.get_cached_prices.return_value = prices

        result = self.service.get_pinned_tickers('u-1')

        assert result is not None
        assert len(result) == 3
        symbols = [t['symbol'] for t in result]
        assert 'AAPL' in symbols
        # Should fill with SPY, BTC (TSLA excluded since already have 3 with AAPL)

    def test_get_pinned_tickers_fills_defaults_for_0_pins(self):
        self.mock_db.get_pinned_items.return_value = []
        self.mock_db.get_cached_prices.return_value = {}

        result = self.service.get_pinned_tickers('u-1')

        assert len(result) == 3
        symbols = [t['symbol'] for t in result]
        assert symbols == ['SPY', 'BTC', 'TSLA']

    def test_pin_item_enforces_max_3(self):
        self.mock_db.count_pinned_items.return_value = 3

        try:
            self.service.pin_item('u-1', 'item-1')
            assert False, "Should raise ValueError"
        except ValueError as e:
            assert '3 pinned' in str(e)

    def test_pin_item_succeeds_when_under_limit(self):
        self.mock_db.count_pinned_items.return_value = 2

        self.service.pin_item('u-1', 'item-1')

        self.mock_db.set_item_pinned.assert_called_once_with('item-1', True)

    def test_unpin_item(self):
        self.service.unpin_item('item-1')
        self.mock_db.set_item_pinned.assert_called_once_with('item-1', False)

    # ── Sections ─────────────────────────────────────────────

    def test_create_section_returns_id(self):
        result = self.service.create_section('wl-1', 'Tech')
        assert self.mock_db.create_section.called
        args = self.mock_db.create_section.call_args[0]
        assert args[1] == 'wl-1'
        assert args[2] == 'Tech'

    # ── get_watchlist_with_items ──────────────────────────────

    def test_get_watchlist_with_items_enriches_prices(self):
        self.mock_db.get_watchlist.return_value = {
            'watchlist_id': 'wl-1', 'name': 'Main', 'user_id': 'u-1'
        }
        self.mock_db.get_watchlist_items.return_value = [
            {'item_id': 'i-1', 'symbol': 'AAPL', 'asset_type': 'stock', 'section_id': None, 'display_name': 'Apple'}
        ]
        self.mock_db.list_sections.return_value = []
        self.mock_db.get_cached_prices.return_value = {
            'AAPL': {'price': Decimal('190'), 'change_percent': Decimal('1.5'), 'last_updated': None}
        }

        result = self.service.get_watchlist_with_items('wl-1')

        assert result is not None
        unsectioned = result['unsectioned_items']
        assert len(unsectioned) == 1
        assert unsectioned[0]['price'] == Decimal('190')
        assert unsectioned[0]['change_percent'] == Decimal('1.5')

    def test_get_watchlist_with_items_returns_none_if_not_found(self):
        self.mock_db.get_watchlist.return_value = None

        result = self.service.get_watchlist_with_items('bad-id')

        assert result is None


class TestDefaultPins:
    def test_default_pins_has_3_entries(self):
        assert len(DEFAULT_PINS) == 3

    def test_default_pins_symbols(self):
        symbols = [d['symbol'] for d in DEFAULT_PINS]
        assert symbols == ['SPY', 'BTC', 'TSLA']

    def test_default_pins_asset_types(self):
        types = {d['symbol']: d['asset_type'] for d in DEFAULT_PINS}
        assert types['SPY'] == 'stock'
        assert types['BTC'] == 'crypto'
        assert types['TSLA'] == 'stock'


class TestGetWatchlistServiceSingleton:
    def test_singleton_returns_same_instance(self):
        s1 = get_watchlist_service()
        s2 = get_watchlist_service()
        assert s1 is s2
