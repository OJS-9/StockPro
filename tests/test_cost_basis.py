"""
Tests for cost basis calculations.
"""

import pytest
from decimal import Decimal
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from portfolio.cost_basis import calculate_simple_average, CostBasisResult


class TestSimpleAverageCostBasis:
    """Tests for simple average cost basis calculation."""

    def test_empty_transactions(self):
        """Empty transaction list should return zeros."""
        result = calculate_simple_average([])

        assert result.total_quantity == Decimal('0')
        assert result.average_cost == Decimal('0')
        assert result.total_cost_basis == Decimal('0')
        assert result.realized_gains == Decimal('0')

    def test_single_buy(self):
        """Single buy should set average cost equal to purchase price."""
        txns = [{
            'transaction_type': 'buy',
            'quantity': 10,
            'price_per_unit': 100,
            'fees': 0,
            'transaction_date': datetime(2024, 1, 1)
        }]

        result = calculate_simple_average(txns)

        assert result.total_quantity == Decimal('10')
        assert result.average_cost == Decimal('100')
        assert result.total_cost_basis == Decimal('1000')
        assert result.realized_gains == Decimal('0')

    def test_single_buy_with_fees(self):
        """Buy with fees should include fees in cost basis."""
        txns = [{
            'transaction_type': 'buy',
            'quantity': 10,
            'price_per_unit': 100,
            'fees': 10,
            'transaction_date': datetime(2024, 1, 1)
        }]

        result = calculate_simple_average(txns)

        assert result.total_quantity == Decimal('10')
        assert result.average_cost == Decimal('101')  # (1000 + 10) / 10
        assert result.total_cost_basis == Decimal('1010')
        assert result.realized_gains == Decimal('0')

    def test_averaging_down(self):
        """Two buys at different prices should average correctly."""
        txns = [
            {
                'transaction_type': 'buy',
                'quantity': 10,
                'price_per_unit': 100,
                'fees': 0,
                'transaction_date': datetime(2024, 1, 1)
            },
            {
                'transaction_type': 'buy',
                'quantity': 10,
                'price_per_unit': 50,
                'fees': 0,
                'transaction_date': datetime(2024, 1, 2)
            },
        ]

        result = calculate_simple_average(txns)

        assert result.total_quantity == Decimal('20')
        assert result.average_cost == Decimal('75')  # (1000 + 500) / 20
        assert result.total_cost_basis == Decimal('1500')
        assert result.realized_gains == Decimal('0')

    def test_averaging_up(self):
        """Two buys at increasing prices should average correctly."""
        txns = [
            {
                'transaction_type': 'buy',
                'quantity': 10,
                'price_per_unit': 50,
                'fees': 0,
                'transaction_date': datetime(2024, 1, 1)
            },
            {
                'transaction_type': 'buy',
                'quantity': 10,
                'price_per_unit': 100,
                'fees': 0,
                'transaction_date': datetime(2024, 1, 2)
            },
        ]

        result = calculate_simple_average(txns)

        assert result.total_quantity == Decimal('20')
        assert result.average_cost == Decimal('75')  # (500 + 1000) / 20
        assert result.total_cost_basis == Decimal('1500')

    def test_partial_sell_with_profit(self):
        """Selling partial position at profit should calculate realized gains."""
        txns = [
            {
                'transaction_type': 'buy',
                'quantity': 10,
                'price_per_unit': 100,
                'fees': 0,
                'transaction_date': datetime(2024, 1, 1)
            },
            {
                'transaction_type': 'sell',
                'quantity': 5,
                'price_per_unit': 120,
                'fees': 0,
                'transaction_date': datetime(2024, 1, 2)
            },
        ]

        result = calculate_simple_average(txns)

        assert result.total_quantity == Decimal('5')
        assert result.average_cost == Decimal('100')  # Unchanged after sell
        assert result.total_cost_basis == Decimal('500')
        assert result.realized_gains == Decimal('100')  # (5 * 120) - (5 * 100)

    def test_partial_sell_with_loss(self):
        """Selling partial position at loss should calculate negative realized gains."""
        txns = [
            {
                'transaction_type': 'buy',
                'quantity': 10,
                'price_per_unit': 100,
                'fees': 0,
                'transaction_date': datetime(2024, 1, 1)
            },
            {
                'transaction_type': 'sell',
                'quantity': 5,
                'price_per_unit': 80,
                'fees': 0,
                'transaction_date': datetime(2024, 1, 2)
            },
        ]

        result = calculate_simple_average(txns)

        assert result.total_quantity == Decimal('5')
        assert result.average_cost == Decimal('100')
        assert result.total_cost_basis == Decimal('500')
        assert result.realized_gains == Decimal('-100')  # (5 * 80) - (5 * 100)

    def test_sell_with_fees(self):
        """Sell fees should reduce realized gains."""
        txns = [
            {
                'transaction_type': 'buy',
                'quantity': 10,
                'price_per_unit': 100,
                'fees': 0,
                'transaction_date': datetime(2024, 1, 1)
            },
            {
                'transaction_type': 'sell',
                'quantity': 5,
                'price_per_unit': 120,
                'fees': 10,
                'transaction_date': datetime(2024, 1, 2)
            },
        ]

        result = calculate_simple_average(txns)

        # Proceeds = (5 * 120) - 10 = 590
        # Cost = 5 * 100 = 500
        # Realized gain = 590 - 500 = 90
        assert result.realized_gains == Decimal('90')

    def test_full_sell(self):
        """Selling entire position should result in zero quantity."""
        txns = [
            {
                'transaction_type': 'buy',
                'quantity': 10,
                'price_per_unit': 100,
                'fees': 0,
                'transaction_date': datetime(2024, 1, 1)
            },
            {
                'transaction_type': 'sell',
                'quantity': 10,
                'price_per_unit': 150,
                'fees': 0,
                'transaction_date': datetime(2024, 1, 2)
            },
        ]

        result = calculate_simple_average(txns)

        assert result.total_quantity == Decimal('0')
        assert result.average_cost == Decimal('0')
        assert result.total_cost_basis == Decimal('0')
        assert result.realized_gains == Decimal('500')  # (10 * 150) - (10 * 100)

    def test_buy_sell_buy(self):
        """Buy, sell all, then buy again should start fresh average."""
        txns = [
            {
                'transaction_type': 'buy',
                'quantity': 10,
                'price_per_unit': 100,
                'fees': 0,
                'transaction_date': datetime(2024, 1, 1)
            },
            {
                'transaction_type': 'sell',
                'quantity': 10,
                'price_per_unit': 150,
                'fees': 0,
                'transaction_date': datetime(2024, 1, 2)
            },
            {
                'transaction_type': 'buy',
                'quantity': 5,
                'price_per_unit': 200,
                'fees': 0,
                'transaction_date': datetime(2024, 1, 3)
            },
        ]

        result = calculate_simple_average(txns)

        assert result.total_quantity == Decimal('5')
        assert result.average_cost == Decimal('200')
        assert result.total_cost_basis == Decimal('1000')
        assert result.realized_gains == Decimal('500')  # From first sell

    def test_multiple_sells(self):
        """Multiple sells should accumulate realized gains."""
        txns = [
            {
                'transaction_type': 'buy',
                'quantity': 10,
                'price_per_unit': 100,
                'fees': 0,
                'transaction_date': datetime(2024, 1, 1)
            },
            {
                'transaction_type': 'sell',
                'quantity': 3,
                'price_per_unit': 120,
                'fees': 0,
                'transaction_date': datetime(2024, 1, 2)
            },
            {
                'transaction_type': 'sell',
                'quantity': 2,
                'price_per_unit': 130,
                'fees': 0,
                'transaction_date': datetime(2024, 1, 3)
            },
        ]

        result = calculate_simple_average(txns)

        assert result.total_quantity == Decimal('5')
        assert result.average_cost == Decimal('100')
        # First sell: (3 * 120) - (3 * 100) = 60
        # Second sell: (2 * 130) - (2 * 100) = 60
        # Total realized: 120
        assert result.realized_gains == Decimal('120')

    def test_decimal_quantities(self):
        """Should handle decimal quantities (crypto)."""
        txns = [
            {
                'transaction_type': 'buy',
                'quantity': '0.5',
                'price_per_unit': '50000',
                'fees': '2.50',
                'transaction_date': datetime(2024, 1, 1)
            },
            {
                'transaction_type': 'buy',
                'quantity': '0.25',
                'price_per_unit': '40000',
                'fees': '1.25',
                'transaction_date': datetime(2024, 1, 2)
            },
        ]

        result = calculate_simple_average(txns)

        assert result.total_quantity == Decimal('0.75')
        # Cost: (0.5 * 50000 + 2.50) + (0.25 * 40000 + 1.25) = 25002.50 + 10001.25 = 35003.75
        # Average: 35003.75 / 0.75 = 46671.666...
        assert result.total_cost_basis == Decimal('35003.75')

    def test_out_of_order_transactions(self):
        """Transactions should be sorted by date before processing."""
        txns = [
            {
                'transaction_type': 'sell',
                'quantity': 5,
                'price_per_unit': 120,
                'fees': 0,
                'transaction_date': datetime(2024, 1, 2)  # Second by date
            },
            {
                'transaction_type': 'buy',
                'quantity': 10,
                'price_per_unit': 100,
                'fees': 0,
                'transaction_date': datetime(2024, 1, 1)  # First by date
            },
        ]

        result = calculate_simple_average(txns)

        # Should process buy first, then sell
        assert result.total_quantity == Decimal('5')
        assert result.average_cost == Decimal('100')
        assert result.realized_gains == Decimal('100')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
