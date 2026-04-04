"""
Tests for CSV importer.
"""

import pytest
from decimal import Decimal
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from portfolio.csv_importer import CSVImporter, ImportResult


class TestCSVImporter:
    """Tests for CSV import functionality."""

    @pytest.fixture
    def importer(self):
        """Create importer instance."""
        return CSVImporter()

    def test_detect_coinbase_format(self, importer):
        """Should detect Coinbase format from headers."""
        headers = ['Timestamp', 'Transaction Type', 'Asset', 'Quantity Transacted', 'Spot Price at Transaction']
        assert importer.detect_format(headers) == 'coinbase'

    def test_detect_robinhood_format(self, importer):
        """Should detect Robinhood format from headers."""
        headers = ['Activity Date', 'Trans Code', 'Instrument', 'Quantity', 'Price']
        assert importer.detect_format(headers) == 'robinhood'

    def test_detect_generic_format(self, importer):
        """Should detect generic format from headers."""
        headers = ['date', 'symbol', 'type', 'quantity', 'price']
        assert importer.detect_format(headers) == 'generic'

    def test_detect_unknown_format(self, importer):
        """Should return None for unknown format."""
        headers = ['foo', 'bar', 'baz']
        assert importer.detect_format(headers) is None

    def test_parse_generic_buy(self, importer):
        """Should parse generic CSV with buy transaction."""
        csv_content = """date,symbol,type,quantity,price,fees,notes
2024-01-15,AAPL,buy,10,185.50,0,Initial purchase"""

        result = importer.parse_csv(csv_content)

        assert result.success_count == 1
        assert result.error_count == 0
        assert len(result.transactions) == 1

        txn = result.transactions[0]
        assert txn['symbol'] == 'AAPL'
        assert txn['transaction_type'] == 'buy'
        assert txn['quantity'] == Decimal('10')
        assert txn['price_per_unit'] == Decimal('185.50')
        assert txn['fees'] == Decimal('0')
        assert txn['notes'] == 'Initial purchase'
        assert txn['transaction_date'] == datetime(2024, 1, 15)

    def test_parse_generic_sell(self, importer):
        """Should parse generic CSV with sell transaction."""
        csv_content = """date,symbol,type,quantity,price,fees,notes
2024-02-01,AAPL,sell,5,190.00,2.50,Taking profits"""

        result = importer.parse_csv(csv_content)

        assert result.success_count == 1
        txn = result.transactions[0]
        assert txn['transaction_type'] == 'sell'
        assert txn['quantity'] == Decimal('5')
        assert txn['price_per_unit'] == Decimal('190.00')
        assert txn['fees'] == Decimal('2.50')

    def test_parse_multiple_transactions(self, importer):
        """Should parse multiple transactions."""
        csv_content = """date,symbol,type,quantity,price,fees,notes
2024-01-15,AAPL,buy,10,185.50,0,
2024-01-20,BTC,buy,0.5,42000,2.50,DCA
2024-02-01,AAPL,sell,5,190.00,0,"""

        result = importer.parse_csv(csv_content)

        assert result.success_count == 3
        assert result.error_count == 0
        assert len(result.transactions) == 3

        # Check BTC transaction
        btc_txn = result.transactions[1]
        assert btc_txn['symbol'] == 'BTC'
        assert btc_txn['quantity'] == Decimal('0.5')
        assert btc_txn['price_per_unit'] == Decimal('42000')

    def test_parse_with_currency_symbols(self, importer):
        """Should handle currency symbols in prices."""
        csv_content = """date,symbol,type,quantity,price,fees,notes
2024-01-15,AAPL,buy,10,$185.50,$5.00,"""

        result = importer.parse_csv(csv_content)

        assert result.success_count == 1
        txn = result.transactions[0]
        assert txn['price_per_unit'] == Decimal('185.50')
        assert txn['fees'] == Decimal('5.00')

    def test_parse_with_commas_in_numbers(self, importer):
        """Should handle commas in large numbers."""
        csv_content = """date,symbol,type,quantity,price,fees,notes
2024-01-15,BTC,buy,1,"50,000.00",0,"""

        result = importer.parse_csv(csv_content)

        assert result.success_count == 1
        txn = result.transactions[0]
        assert txn['price_per_unit'] == Decimal('50000.00')

    def test_parse_us_date_format(self, importer):
        """Should handle US date format (MM/DD/YYYY)."""
        csv_content = """date,symbol,type,quantity,price,fees,notes
01/15/2024,AAPL,buy,10,185.50,0,"""

        result = importer.parse_csv(csv_content)

        assert result.success_count == 1
        txn = result.transactions[0]
        assert txn['transaction_date'] == datetime(2024, 1, 15)

    def test_parse_iso_date_format(self, importer):
        """Should handle ISO date format."""
        csv_content = """date,symbol,type,quantity,price,fees,notes
2024-01-15T10:30:00Z,AAPL,buy,10,185.50,0,"""

        result = importer.parse_csv(csv_content)

        assert result.success_count == 1
        txn = result.transactions[0]
        assert txn['transaction_date'].year == 2024
        assert txn['transaction_date'].month == 1
        assert txn['transaction_date'].day == 15

    def test_skip_non_buy_sell_transactions(self, importer):
        """Should skip transactions that aren't buy/sell."""
        csv_content = """date,symbol,type,quantity,price,fees,notes
2024-01-15,AAPL,buy,10,185.50,0,
2024-01-16,BTC,transfer,0.5,0,0,
2024-01-17,ETH,reward,0.1,0,0,
2024-01-18,AAPL,sell,5,190.00,0,"""

        result = importer.parse_csv(csv_content)

        # Should only have buy and sell
        assert result.success_count == 2
        assert all(t['transaction_type'] in ('buy', 'sell') for t in result.transactions)

    def test_error_missing_symbol(self, importer):
        """Should report error for missing symbol."""
        csv_content = """date,symbol,type,quantity,price,fees,notes
2024-01-15,,buy,10,185.50,0,"""

        result = importer.parse_csv(csv_content)

        assert result.success_count == 0
        assert result.error_count == 1
        assert 'symbol' in result.errors[0]['error'].lower()

    def test_error_invalid_quantity(self, importer):
        """Should report error for invalid quantity."""
        csv_content = """date,symbol,type,quantity,price,fees,notes
2024-01-15,AAPL,buy,0,185.50,0,"""

        result = importer.parse_csv(csv_content)

        assert result.success_count == 0
        assert result.error_count == 1
        assert 'quantity' in result.errors[0]['error'].lower()

    def test_error_invalid_price(self, importer):
        """Should report error for invalid price."""
        csv_content = """date,symbol,type,quantity,price,fees,notes
2024-01-15,AAPL,buy,10,0,0,"""

        result = importer.parse_csv(csv_content)

        assert result.success_count == 0
        assert result.error_count == 1
        assert 'price' in result.errors[0]['error'].lower()

    def test_error_invalid_date(self, importer):
        """Should report error for invalid date."""
        csv_content = """date,symbol,type,quantity,price,fees,notes
not-a-date,AAPL,buy,10,185.50,0,"""

        result = importer.parse_csv(csv_content)

        assert result.success_count == 0
        assert result.error_count == 1
        assert 'date' in result.errors[0]['error'].lower()

    def test_unknown_format_error(self, importer):
        """Should return error for unknown CSV format."""
        csv_content = """foo,bar,baz
1,2,3"""

        result = importer.parse_csv(csv_content)

        assert result.success_count == 0
        assert result.error_count == 1
        assert 'format' in result.errors[0]['error'].lower()

    def test_case_insensitive_type(self, importer):
        """Should handle different cases for transaction type."""
        csv_content = """date,symbol,type,quantity,price,fees,notes
2024-01-15,AAPL,BUY,10,185.50,0,
2024-01-16,AAPL,Sell,5,190.00,0,"""

        result = importer.parse_csv(csv_content)

        assert result.success_count == 2
        assert result.transactions[0]['transaction_type'] == 'buy'
        assert result.transactions[1]['transaction_type'] == 'sell'

    def test_empty_csv(self, importer):
        """Should handle empty CSV (headers only)."""
        csv_content = """date,symbol,type,quantity,price,fees,notes"""

        result = importer.parse_csv(csv_content)

        assert result.success_count == 0
        assert result.error_count == 0
        assert len(result.transactions) == 0

    def test_optional_fees_column(self, importer):
        """Should handle missing fees column."""
        csv_content = """date,symbol,type,quantity,price,notes
2024-01-15,AAPL,buy,10,185.50,Purchase"""

        result = importer.parse_csv(csv_content)

        assert result.success_count == 1
        txn = result.transactions[0]
        assert txn['fees'] == Decimal('0')

    def test_preview_csv(self, importer):
        """Should preview CSV content."""
        csv_content = """date,symbol,type,quantity,price,fees,notes
2024-01-15,AAPL,buy,10,185.50,0,First
2024-01-16,BTC,buy,0.5,42000,0,Second
2024-01-17,ETH,buy,1,2500,0,Third"""

        preview = importer.preview_csv(csv_content, max_rows=2)

        assert preview['format'] == 'generic'
        assert preview['format_detected'] is True
        assert len(preview['headers']) == 7
        assert len(preview['sample_rows']) == 2

    def test_coinbase_format(self, importer):
        """Should parse Coinbase format."""
        csv_content = """Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price at Transaction,Fees and/or Spread,Notes
2024-01-15T10:30:00Z,Buy,BTC,0.5,42000,10,
2024-01-16T11:00:00Z,Sell,ETH,1,2500,5,"""

        result = importer.parse_csv(csv_content, format_type='coinbase')

        assert result.success_count == 2
        assert result.transactions[0]['symbol'] == 'BTC'
        assert result.transactions[0]['transaction_type'] == 'buy'
        assert result.transactions[1]['symbol'] == 'ETH'
        assert result.transactions[1]['transaction_type'] == 'sell'


class TestImportResult:
    """Tests for ImportResult dataclass."""

    def test_default_values(self):
        """Should have correct default values."""
        result = ImportResult(success_count=0, error_count=0)

        assert result.transactions == []
        assert result.errors == []


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
