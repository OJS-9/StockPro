"""
Tests for PortfolioHistoryService.
"""

import pytest
from decimal import Decimal
from datetime import datetime, date
from unittest.mock import MagicMock, patch

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from portfolio.history_service import PortfolioHistoryService


def make_txn(symbol, asset_type, txn_type, qty, price, txn_date):
    return {
        'symbol': symbol,
        'asset_type': asset_type,
        'transaction_type': txn_type,
        'quantity': Decimal(str(qty)),
        'price_per_unit': Decimal(str(price)),
        'transaction_date': txn_date,
        'fees': Decimal('0'),
    }


class TestPortfolioHistoryService:

    def setup_method(self):
        self.db = MagicMock()
        self.service = PortfolioHistoryService(db=self.db)

    def test_returns_list_of_dicts(self):
        """get_monthly_values returns a list."""
        self.db.get_all_portfolio_transactions.return_value = []
        result = self.service.get_monthly_values('portfolio-1')
        assert isinstance(result, list)

    def test_returns_12_months_by_default(self):
        """Returns 12 month entries by default."""
        self.db.get_all_portfolio_transactions.return_value = []
        result = self.service.get_monthly_values('portfolio-1')
        assert len(result) == 12

    def test_each_entry_has_date_and_value(self):
        """Each entry has 'date' (string) and 'value' (float)."""
        self.db.get_all_portfolio_transactions.return_value = []
        result = self.service.get_monthly_values('portfolio-1')
        for entry in result:
            assert 'date' in entry
            assert 'value' in entry
            assert isinstance(entry['date'], str)
            assert isinstance(entry['value'], float)

    def test_zero_value_when_no_transactions(self):
        """All months are 0.0 when portfolio has no transactions."""
        self.db.get_all_portfolio_transactions.return_value = []
        result = self.service.get_monthly_values('portfolio-1')
        for entry in result:
            assert entry['value'] == 0.0

    def test_holding_acquired_after_month_end_contributes_nothing(self):
        """A buy after a month-end date contributes 0 value for that month."""
        # Transaction dated very recently — should not affect most historical months
        txn = make_txn('AAPL', 'stock', 'buy', 10, 150, datetime(2099, 1, 1))
        self.db.get_all_portfolio_transactions.return_value = [txn]

        with patch.object(self.service, '_get_stock_prices', return_value={'2099-01-31': 200.0}):
            result = self.service.get_monthly_values('portfolio-1')

        # All months in normal 12-month window should be 0
        for entry in result:
            assert entry['value'] == 0.0

    def test_sell_clamped_to_zero(self):
        """Sells that bring quantity negative are clamped to 0."""
        buy = make_txn('AAPL', 'stock', 'buy', 5, 100, datetime(2020, 1, 1))
        sell = make_txn('AAPL', 'stock', 'sell', 10, 100, datetime(2020, 2, 1))
        self.db.get_all_portfolio_transactions.return_value = [buy, sell]

        with patch.object(self.service, '_get_stock_prices', return_value={}):
            result = self.service.get_monthly_values('portfolio-1')

        for entry in result:
            assert entry['value'] >= 0.0

    def test_skips_symbol_when_price_unavailable(self):
        """If price fetch fails for a symbol, that symbol contributes 0 (no error)."""
        txn = make_txn('UNKNOWNSYM', 'stock', 'buy', 5, 100, datetime(2020, 1, 1))
        self.db.get_all_portfolio_transactions.return_value = [txn]

        with patch.object(self.service, '_get_stock_prices', return_value={}):
            result = self.service.get_monthly_values('portfolio-1')

        assert isinstance(result, list)
        assert len(result) == 12

    def test_custom_months_parameter(self):
        """Accepts a custom months parameter."""
        self.db.get_all_portfolio_transactions.return_value = []
        result = self.service.get_monthly_values('portfolio-1', months=6)
        assert len(result) == 6

    def test_date_format_is_readable(self):
        """Date strings look like 'Jan 2025'."""
        self.db.get_all_portfolio_transactions.return_value = []
        result = self.service.get_monthly_values('portfolio-1', months=1)
        # Should have a month name abbreviation + space + 4-digit year
        import re
        assert re.match(r'[A-Z][a-z]{2} \d{4}', result[0]['date'])
