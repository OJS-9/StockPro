"""
Portfolio service - main business logic for portfolio operations.
"""

import uuid
import sys
import os
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .cost_basis import calculate_simple_average, CostBasisResult
from .csv_importer import CSVImporter, ImportResult


class PortfolioService:
    """Main service for portfolio operations."""

    def __init__(self):
        """Initialize portfolio service."""
        self._db = None
        self._provider_factory = None
        self.csv_importer = CSVImporter()

    @property
    def db(self):
        """Lazy database initialization."""
        if self._db is None:
            from database import get_database_manager
            self._db = get_database_manager()
        return self._db

    @property
    def provider_factory(self):
        """Lazy provider factory initialization."""
        if self._provider_factory is None:
            from data_providers import DataProviderFactory
            self._provider_factory = DataProviderFactory
        return self._provider_factory

    # ==================== Portfolio CRUD ====================

    def create_portfolio(
        self,
        name: str = "My Portfolio",
        description: str = ""
    ) -> str:
        """
        Create a new portfolio.

        Args:
            name: Portfolio name
            description: Portfolio description

        Returns:
            portfolio_id: Generated portfolio ID
        """
        portfolio_id = str(uuid.uuid4())
        self.db.create_portfolio(portfolio_id, name, description)
        return portfolio_id

    def get_portfolio(self, portfolio_id: str) -> Optional[Dict]:
        """
        Get portfolio by ID.

        Args:
            portfolio_id: Portfolio ID

        Returns:
            Portfolio dict or None
        """
        return self.db.get_portfolio(portfolio_id)

    def list_portfolios(self) -> List[Dict]:
        """
        List all portfolios.

        Returns:
            List of portfolio dicts
        """
        return self.db.list_portfolios()

    def get_default_portfolio(self) -> Dict:
        """
        Get or create the default portfolio.

        Returns:
            Default portfolio dict
        """
        portfolios = self.db.list_portfolios()
        if portfolios:
            return portfolios[0]

        # Create default portfolio
        portfolio_id = self.create_portfolio()
        return self.get_portfolio(portfolio_id)

    # ==================== Holdings ====================

    def get_holdings(self, portfolio_id: str) -> List[Dict]:
        """
        Get all holdings for a portfolio with current prices.

        Args:
            portfolio_id: Portfolio ID

        Returns:
            List of holding dicts with computed fields:
            - current_price
            - market_value
            - unrealized_gain
            - unrealized_gain_pct
        """
        holdings = self.db.get_holdings(portfolio_id)
        
        # Filter out holdings with zero quantity (closed positions)
        holdings = [h for h in holdings if h.get('total_quantity', Decimal('0')) > Decimal('0')]

        # Group by asset type for efficient price fetching
        stocks = [h for h in holdings if h['asset_type'] == 'stock']
        cryptos = [h for h in holdings if h['asset_type'] == 'crypto']

        # Fetch stock prices
        if stocks:
            stock_provider = self.provider_factory.get_provider('stock')
            stock_symbols = [h['symbol'] for h in stocks]
            stock_prices = stock_provider.get_prices_batch(stock_symbols)
            for h in stocks:
                price = stock_prices.get(h['symbol'])
                h['current_price'] = price if price is not None else Decimal('0')
                h['price_available'] = price is not None

        # Fetch crypto prices
        if cryptos:
            crypto_provider = self.provider_factory.get_provider('crypto')
            crypto_symbols = [h['symbol'] for h in cryptos]
            crypto_prices = crypto_provider.get_prices_batch(crypto_symbols)
            for h in cryptos:
                price = crypto_prices.get(h['symbol'])
                h['current_price'] = price if price is not None else Decimal('0')
                h['price_available'] = price is not None

        # Calculate market value and gains for all holdings
        for h in holdings:
            current_price = h.get('current_price', Decimal('0'))
            price_available = h.get('price_available', False)
            total_quantity = h.get('total_quantity', Decimal('0'))
            total_cost_basis = h.get('total_cost_basis', Decimal('0'))

            if not price_available:
                # Can't compute meaningful values without a real price
                h['market_value'] = None
                h['unrealized_gain'] = None
                h['unrealized_gain_pct'] = None
            else:
                h['market_value'] = total_quantity * current_price
                h['unrealized_gain'] = h['market_value'] - total_cost_basis

                if total_cost_basis > 0:
                    h['unrealized_gain_pct'] = (h['unrealized_gain'] / total_cost_basis) * 100
                else:
                    h['unrealized_gain_pct'] = Decimal('0')

        return holdings

    def get_holding(self, portfolio_id: str, symbol: str) -> Optional[Dict]:
        """
        Get a specific holding.

        Args:
            portfolio_id: Portfolio ID
            symbol: Asset symbol

        Returns:
            Holding dict or None
        """
        return self.db.get_holding(portfolio_id, symbol)

    def get_holding_by_id(self, holding_id: str) -> Optional[Dict]:
        """
        Get a holding by its ID.

        Args:
            holding_id: Holding ID

        Returns:
            Holding dict or None
        """
        return self.db.get_holding_by_id(holding_id)

    # ==================== Transactions ====================

    def add_transaction(
        self,
        portfolio_id: str,
        symbol: str,
        transaction_type: str,
        quantity: Decimal,
        price_per_unit: Decimal,
        transaction_date: datetime,
        fees: Decimal = Decimal('0'),
        notes: str = "",
        asset_type: Optional[str] = None
    ) -> str:
        """
        Add a transaction and recalculate holding.

        Args:
            portfolio_id: Portfolio ID
            symbol: Asset symbol
            transaction_type: 'buy' or 'sell'
            quantity: Transaction quantity
            price_per_unit: Price per unit
            transaction_date: Date of transaction
            fees: Transaction fees (optional)
            notes: Transaction notes (optional)
            asset_type: 'stock' or 'crypto' (auto-detected if not provided)

        Returns:
            transaction_id: Generated transaction ID
        """
        # Normalize symbol
        symbol = symbol.upper().replace('CRYPTO:', '').strip()

        # Auto-detect asset type if not provided
        if asset_type is None:
            asset_type = self.provider_factory.detect_asset_type(symbol)

        # Validate transaction type
        if transaction_type not in ('buy', 'sell'):
            raise ValueError(f"Invalid transaction type: {transaction_type}")

        # Get or create holding
        holding = self.db.get_holding(portfolio_id, symbol)
        if holding is None:
            holding_id = str(uuid.uuid4())
            self.db.create_holding(holding_id, portfolio_id, symbol, asset_type)
        else:
            holding_id = holding['holding_id']

        # Add transaction
        transaction_id = str(uuid.uuid4())
        self.db.add_transaction(
            transaction_id=transaction_id,
            holding_id=holding_id,
            transaction_type=transaction_type,
            quantity=quantity,
            price_per_unit=price_per_unit,
            fees=fees,
            transaction_date=transaction_date,
            notes=notes,
            import_source='manual'
        )

        # Recalculate holding totals
        self._recalculate_holding(holding_id)

        return transaction_id

    def get_transactions(self, holding_id: str) -> List[Dict]:
        """
        Get all transactions for a holding.

        Args:
            holding_id: Holding ID

        Returns:
            List of transaction dicts
        """
        return self.db.get_transactions(holding_id)

    def get_transaction(self, transaction_id: str) -> Optional[Dict]:
        """
        Get a single transaction.

        Args:
            transaction_id: Transaction ID

        Returns:
            Transaction dict or None
        """
        return self.db.get_transaction(transaction_id)

    def delete_transaction(self, transaction_id: str) -> bool:
        """
        Delete a transaction and recalculate holding.

        Args:
            transaction_id: Transaction ID

        Returns:
            True if deleted, False if not found
        """
        txn = self.db.get_transaction(transaction_id)
        if not txn:
            return False

        holding_id = txn['holding_id']
        self.db.delete_transaction(transaction_id)
        self._recalculate_holding(holding_id)
        return True

    def _recalculate_holding(self, holding_id: str):
        """
        Recalculate holding totals from transactions.

        Args:
            holding_id: Holding ID
        """
        transactions = self.db.get_transactions(holding_id)

        if not transactions:
            # No transactions left — delete the holding row entirely so it
            # doesn't appear as a ghost row in exports or future queries.
            self.db.delete_holding(holding_id)
            return

        # Calculate using simple average method
        result = calculate_simple_average(transactions)

        self.db.update_holding(
            holding_id=holding_id,
            total_quantity=result.total_quantity,
            average_cost=result.average_cost,
            total_cost_basis=result.total_cost_basis
        )

    # ==================== CSV Import ====================

    def import_csv(
        self,
        portfolio_id: str,
        csv_content: str,
        filename: str
    ) -> ImportResult:
        """
        Import transactions from CSV.

        Args:
            portfolio_id: Portfolio ID
            csv_content: Raw CSV string content
            filename: Original filename for logging

        Returns:
            ImportResult with success/error counts
        """
        # Parse CSV
        result = self.csv_importer.parse_csv(csv_content)

        # Add each transaction
        successful = 0
        for txn in result.transactions:
            try:
                self.add_transaction(
                    portfolio_id=portfolio_id,
                    symbol=txn['symbol'],
                    transaction_type=txn['transaction_type'],
                    quantity=txn['quantity'],
                    price_per_unit=txn['price_per_unit'],
                    transaction_date=txn['transaction_date'],
                    fees=txn['fees'],
                    notes=txn.get('notes', ''),
                )
                successful += 1
            except Exception as e:
                result.errors.append({
                    'row': 'import',
                    'error': str(e),
                    'data': txn
                })

        # Update counts
        result.success_count = successful
        result.error_count = len(result.errors)

        # Log import
        import_id = str(uuid.uuid4())
        self.db.log_csv_import(
            import_id=import_id,
            portfolio_id=portfolio_id,
            filename=filename,
            row_count=len(result.transactions) + len(result.errors),
            success_count=result.success_count,
            error_count=result.error_count,
            errors_json=result.errors
        )

        return result

    def preview_csv(self, csv_content: str) -> Dict:
        """
        Preview CSV content without importing.

        Args:
            csv_content: Raw CSV string

        Returns:
            Preview dict with format, headers, sample rows
        """
        return self.csv_importer.preview_csv(csv_content)

    # ==================== Portfolio Summary ====================

    def get_portfolio_summary(self, portfolio_id: str) -> Dict:
        """
        Get portfolio summary with totals and allocation.

        Args:
            portfolio_id: Portfolio ID

        Returns:
            Summary dict with:
            - total_cost_basis
            - total_market_value
            - total_unrealized_gain
            - total_unrealized_gain_pct
            - holdings_count
            - stock_value, crypto_value
            - stock_allocation_pct, crypto_allocation_pct
            - holdings (list)
        """
        holdings = self.get_holdings(portfolio_id)

        total_cost_basis = sum(
            h.get('total_cost_basis', Decimal('0')) for h in holdings
        )
        total_market_value = sum(
            h.get('market_value') or Decimal('0') for h in holdings
        )
        total_unrealized_gain = total_market_value - total_cost_basis

        if total_cost_basis > 0:
            total_unrealized_gain_pct = (total_unrealized_gain / total_cost_basis) * 100
        else:
            total_unrealized_gain_pct = Decimal('0')

        # Allocation by asset type
        stock_value = sum(
            h.get('market_value') or Decimal('0')
            for h in holdings if h['asset_type'] == 'stock'
        )
        crypto_value = sum(
            h.get('market_value') or Decimal('0')
            for h in holdings if h['asset_type'] == 'crypto'
        )

        if total_market_value > 0:
            stock_allocation_pct = (stock_value / total_market_value) * 100
            crypto_allocation_pct = (crypto_value / total_market_value) * 100
        else:
            stock_allocation_pct = Decimal('0')
            crypto_allocation_pct = Decimal('0')

        return {
            'portfolio_id': portfolio_id,
            'total_cost_basis': total_cost_basis,
            'total_market_value': total_market_value,
            'total_unrealized_gain': total_unrealized_gain,
            'total_unrealized_gain_pct': total_unrealized_gain_pct,
            'holdings_count': len(holdings),
            'stock_value': stock_value,
            'crypto_value': crypto_value,
            'stock_allocation_pct': stock_allocation_pct,
            'crypto_allocation_pct': crypto_allocation_pct,
            'holdings': holdings,
        }


# Global service instance
_portfolio_service: Optional[PortfolioService] = None


def get_portfolio_service() -> PortfolioService:
    """Get or create global portfolio service instance."""
    global _portfolio_service
    if _portfolio_service is None:
        _portfolio_service = PortfolioService()
    return _portfolio_service
