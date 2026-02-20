# Portfolio Feature Implementation Plan

## Overview

Add portfolio tracking with support for stocks and cryptocurrencies, including position averaging (simple average cost basis), manual transaction entry, and CSV import functionality.

---

## Phase 1: Database Schema

### New Tables

```sql
-- User portfolios (supports multiple portfolios per user)
CREATE TABLE portfolios (
    portfolio_id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(100) NOT NULL DEFAULT 'My Portfolio',
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Holdings aggregate view (computed from transactions)
CREATE TABLE holdings (
    holding_id VARCHAR(36) PRIMARY KEY,
    portfolio_id VARCHAR(36) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    asset_type ENUM('stock', 'crypto') NOT NULL,
    total_quantity DECIMAL(18, 8) NOT NULL DEFAULT 0,
    average_cost DECIMAL(18, 8) NOT NULL DEFAULT 0,
    total_cost_basis DECIMAL(18, 2) NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
    UNIQUE KEY unique_portfolio_symbol (portfolio_id, symbol)
);

-- Individual transactions (source of truth)
CREATE TABLE transactions (
    transaction_id VARCHAR(36) PRIMARY KEY,
    holding_id VARCHAR(36) NOT NULL,
    transaction_type ENUM('buy', 'sell') NOT NULL,
    quantity DECIMAL(18, 8) NOT NULL,
    price_per_unit DECIMAL(18, 8) NOT NULL,
    fees DECIMAL(18, 2) DEFAULT 0,
    transaction_date TIMESTAMP NOT NULL,
    notes TEXT,
    import_source VARCHAR(50),  -- 'manual', 'coinbase', 'robinhood', 'csv'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (holding_id) REFERENCES holdings(holding_id) ON DELETE CASCADE
);

-- CSV import history for tracking and rollback
CREATE TABLE csv_imports (
    import_id VARCHAR(36) PRIMARY KEY,
    portfolio_id VARCHAR(36) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    row_count INT NOT NULL,
    success_count INT NOT NULL,
    error_count INT NOT NULL,
    errors_json JSON,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (portfolio_id) REFERENCES portfolios(portfolio_id) ON DELETE CASCADE
);
```

### Files to Modify
- `src/database.py` - Add new table creation in `init_schema()` and CRUD methods

---

## Phase 2: Data Providers

### Abstract Base Provider

```python
# src/data_providers/base_provider.py
from abc import ABC, abstractmethod
from typing import Dict, Optional
from decimal import Decimal

class BaseDataProvider(ABC):
    """Abstract interface for price data providers."""

    @abstractmethod
    def get_current_price(self, symbol: str) -> Optional[Decimal]:
        """Get current price for a symbol."""
        pass

    @abstractmethod
    def get_prices_batch(self, symbols: list[str]) -> Dict[str, Decimal]:
        """Get current prices for multiple symbols."""
        pass

    @abstractmethod
    def validate_symbol(self, symbol: str) -> bool:
        """Check if symbol is valid."""
        pass

    @abstractmethod
    def get_asset_info(self, symbol: str) -> Optional[Dict]:
        """Get basic info (name, market cap, etc.)."""
        pass
```

### Stock Provider (Alpha Vantage)

```python
# src/data_providers/stock_provider.py
from .base_provider import BaseDataProvider
from mcp_tools import call_mcp_tool

class StockDataProvider(BaseDataProvider):
    """Stock data provider using Alpha Vantage MCP."""

    def get_current_price(self, symbol: str) -> Optional[Decimal]:
        """Get current stock price from OVERVIEW tool."""
        try:
            result = call_mcp_tool("OVERVIEW", {"symbol": symbol})
            # Parse price from result
            return Decimal(str(result.get('price', 0)))
        except Exception:
            return None

    def get_prices_batch(self, symbols: list[str]) -> Dict[str, Decimal]:
        """Get prices for multiple stocks (sequential due to API limits)."""
        prices = {}
        for symbol in symbols:
            price = self.get_current_price(symbol)
            if price:
                prices[symbol] = price
        return prices

    def validate_symbol(self, symbol: str) -> bool:
        """Validate stock ticker exists."""
        return self.get_current_price(symbol) is not None

    def get_asset_info(self, symbol: str) -> Optional[Dict]:
        """Get company overview."""
        try:
            return call_mcp_tool("OVERVIEW", {"symbol": symbol})
        except Exception:
            return None
```

### Crypto Provider (CoinGecko)

```python
# src/data_providers/crypto_provider.py
import requests
from .base_provider import BaseDataProvider
from decimal import Decimal
from typing import Dict, Optional

class CryptoDataProvider(BaseDataProvider):
    """Crypto data provider using CoinGecko API."""

    BASE_URL = "https://api.coingecko.com/api/v3"

    # Common symbol to CoinGecko ID mapping
    SYMBOL_MAP = {
        'BTC': 'bitcoin',
        'ETH': 'ethereum',
        'SOL': 'solana',
        'ADA': 'cardano',
        'DOT': 'polkadot',
        'MATIC': 'polygon',
        'AVAX': 'avalanche-2',
        'LINK': 'chainlink',
        'UNI': 'uniswap',
        'ATOM': 'cosmos',
        # Add more as needed
    }

    def __init__(self):
        self._coin_list_cache = None

    def _get_coin_id(self, symbol: str) -> Optional[str]:
        """Convert symbol to CoinGecko coin ID."""
        symbol_upper = symbol.upper()
        if symbol_upper in self.SYMBOL_MAP:
            return self.SYMBOL_MAP[symbol_upper]

        # Fallback: search coin list
        if self._coin_list_cache is None:
            resp = requests.get(f"{self.BASE_URL}/coins/list")
            if resp.ok:
                self._coin_list_cache = resp.json()

        if self._coin_list_cache:
            for coin in self._coin_list_cache:
                if coin['symbol'].upper() == symbol_upper:
                    return coin['id']
        return None

    def get_current_price(self, symbol: str) -> Optional[Decimal]:
        """Get current crypto price."""
        coin_id = self._get_coin_id(symbol)
        if not coin_id:
            return None

        try:
            resp = requests.get(
                f"{self.BASE_URL}/simple/price",
                params={"ids": coin_id, "vs_currencies": "usd"}
            )
            if resp.ok:
                data = resp.json()
                return Decimal(str(data[coin_id]['usd']))
        except Exception:
            pass
        return None

    def get_prices_batch(self, symbols: list[str]) -> Dict[str, Decimal]:
        """Get prices for multiple cryptos in one call."""
        coin_ids = []
        symbol_to_id = {}

        for symbol in symbols:
            coin_id = self._get_coin_id(symbol)
            if coin_id:
                coin_ids.append(coin_id)
                symbol_to_id[coin_id] = symbol.upper()

        if not coin_ids:
            return {}

        try:
            resp = requests.get(
                f"{self.BASE_URL}/simple/price",
                params={"ids": ",".join(coin_ids), "vs_currencies": "usd"}
            )
            if resp.ok:
                data = resp.json()
                prices = {}
                for coin_id, price_data in data.items():
                    symbol = symbol_to_id.get(coin_id)
                    if symbol:
                        prices[symbol] = Decimal(str(price_data['usd']))
                return prices
        except Exception:
            pass
        return {}

    def validate_symbol(self, symbol: str) -> bool:
        """Check if crypto symbol is valid."""
        return self._get_coin_id(symbol) is not None

    def get_asset_info(self, symbol: str) -> Optional[Dict]:
        """Get detailed coin info."""
        coin_id = self._get_coin_id(symbol)
        if not coin_id:
            return None

        try:
            resp = requests.get(f"{self.BASE_URL}/coins/{coin_id}")
            if resp.ok:
                data = resp.json()
                return {
                    'name': data['name'],
                    'symbol': data['symbol'].upper(),
                    'market_cap': data['market_data']['market_cap']['usd'],
                    'volume_24h': data['market_data']['total_volume']['usd'],
                    'price_change_24h': data['market_data']['price_change_percentage_24h'],
                    'circulating_supply': data['market_data']['circulating_supply'],
                    'total_supply': data['market_data']['total_supply'],
                }
        except Exception:
            pass
        return None
```

### Provider Factory

```python
# src/data_providers/provider_factory.py
from .stock_provider import StockDataProvider
from .crypto_provider import CryptoDataProvider
from .base_provider import BaseDataProvider

class DataProviderFactory:
    """Factory to get appropriate data provider based on asset type."""

    _stock_provider = None
    _crypto_provider = None

    # Known crypto symbols for quick detection
    CRYPTO_SYMBOLS = {
        'BTC', 'ETH', 'SOL', 'ADA', 'DOT', 'MATIC', 'AVAX',
        'LINK', 'UNI', 'ATOM', 'XRP', 'DOGE', 'SHIB', 'LTC',
        'BCH', 'XLM', 'ALGO', 'VET', 'FIL', 'AAVE', 'MKR',
    }

    @classmethod
    def get_provider(cls, asset_type: str) -> BaseDataProvider:
        """Get provider for specified asset type."""
        if asset_type == 'crypto':
            if cls._crypto_provider is None:
                cls._crypto_provider = CryptoDataProvider()
            return cls._crypto_provider
        else:
            if cls._stock_provider is None:
                cls._stock_provider = StockDataProvider()
            return cls._stock_provider

    @classmethod
    def detect_asset_type(cls, symbol: str) -> str:
        """Auto-detect if symbol is stock or crypto."""
        symbol_upper = symbol.upper()

        # Check known crypto symbols
        if symbol_upper in cls.CRYPTO_SYMBOLS:
            return 'crypto'

        # Check for CRYPTO: prefix
        if symbol_upper.startswith('CRYPTO:'):
            return 'crypto'

        # Default to stock
        return 'stock'

    @classmethod
    def get_provider_for_symbol(cls, symbol: str) -> tuple[BaseDataProvider, str]:
        """Get provider and detected asset type for a symbol."""
        asset_type = cls.detect_asset_type(symbol)
        return cls.get_provider(asset_type), asset_type
```

### Files to Create
- `src/data_providers/__init__.py`
- `src/data_providers/base_provider.py`
- `src/data_providers/stock_provider.py`
- `src/data_providers/crypto_provider.py`
- `src/data_providers/provider_factory.py`

---

## Phase 3: Portfolio Service Layer

### Cost Basis Calculator

```python
# src/portfolio/cost_basis.py
from decimal import Decimal
from typing import List, Dict
from dataclasses import dataclass

@dataclass
class CostBasisResult:
    total_quantity: Decimal
    average_cost: Decimal
    total_cost_basis: Decimal
    realized_gains: Decimal

def calculate_simple_average(transactions: List[Dict]) -> CostBasisResult:
    """
    Calculate simple average cost basis.

    BUY: Increases quantity and cost basis
    SELL: Decreases quantity proportionally, cost basis adjusts

    Args:
        transactions: List of dicts with keys:
            - transaction_type: 'buy' or 'sell'
            - quantity: Decimal
            - price_per_unit: Decimal
            - fees: Decimal
            - transaction_date: datetime

    Returns:
        CostBasisResult with computed values
    """
    total_quantity = Decimal('0')
    total_cost = Decimal('0')
    realized_gains = Decimal('0')

    # Sort by date
    sorted_txns = sorted(transactions, key=lambda x: x['transaction_date'])

    for txn in sorted_txns:
        qty = Decimal(str(txn['quantity']))
        price = Decimal(str(txn['price_per_unit']))
        fees = Decimal(str(txn.get('fees', 0)))

        if txn['transaction_type'] == 'buy':
            # Add to position
            purchase_cost = (qty * price) + fees
            total_cost += purchase_cost
            total_quantity += qty

        elif txn['transaction_type'] == 'sell':
            if total_quantity > 0:
                # Calculate average cost at time of sale
                avg_cost_at_sale = total_cost / total_quantity

                # Calculate realized gain/loss
                sale_proceeds = (qty * price) - fees
                cost_of_sold = qty * avg_cost_at_sale
                realized_gains += sale_proceeds - cost_of_sold

                # Reduce position
                total_quantity -= qty
                total_cost = avg_cost_at_sale * total_quantity

    average_cost = total_cost / total_quantity if total_quantity > 0 else Decimal('0')

    return CostBasisResult(
        total_quantity=total_quantity,
        average_cost=average_cost,
        total_cost_basis=total_cost,
        realized_gains=realized_gains
    )
```

### CSV Importer

```python
# src/portfolio/csv_importer.py
import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass

@dataclass
class ImportResult:
    success_count: int
    error_count: int
    transactions: List[Dict]
    errors: List[Dict]

class CSVImporter:
    """Import transactions from CSV files."""

    # Supported formats with column mappings
    FORMATS = {
        'coinbase': {
            'date': 'Timestamp',
            'type': 'Transaction Type',
            'symbol': 'Asset',
            'quantity': 'Quantity Transacted',
            'price': 'Spot Price at Transaction',
            'fees': 'Fees and/or Spread',
            'notes': 'Notes',
        },
        'robinhood': {
            'date': 'Activity Date',
            'type': 'Trans Code',
            'symbol': 'Instrument',
            'quantity': 'Quantity',
            'price': 'Price',
            'fees': None,  # Robinhood has no fees column
            'notes': 'Description',
        },
        'generic': {
            'date': 'date',
            'type': 'type',
            'symbol': 'symbol',
            'quantity': 'quantity',
            'price': 'price',
            'fees': 'fees',
            'notes': 'notes',
        }
    }

    # Type mappings for different formats
    TYPE_MAPPINGS = {
        'coinbase': {
            'Buy': 'buy',
            'Sell': 'sell',
            'Advanced Trade Buy': 'buy',
            'Advanced Trade Sell': 'sell',
        },
        'robinhood': {
            'Buy': 'buy',
            'Sell': 'sell',
            'BUY': 'buy',
            'SELL': 'sell',
        },
        'generic': {
            'buy': 'buy',
            'sell': 'sell',
            'BUY': 'buy',
            'SELL': 'sell',
        }
    }

    def detect_format(self, headers: List[str]) -> Optional[str]:
        """Detect CSV format based on headers."""
        headers_lower = [h.lower() for h in headers]

        if 'timestamp' in headers_lower and 'asset' in headers_lower:
            return 'coinbase'
        elif 'activity date' in headers_lower and 'instrument' in headers_lower:
            return 'robinhood'
        elif 'date' in headers_lower and 'symbol' in headers_lower:
            return 'generic'
        return None

    def parse_csv(self, csv_content: str, format_type: Optional[str] = None) -> ImportResult:
        """
        Parse CSV content into transactions.

        Args:
            csv_content: Raw CSV string
            format_type: Optional format override ('coinbase', 'robinhood', 'generic')

        Returns:
            ImportResult with parsed transactions and errors
        """
        transactions = []
        errors = []

        reader = csv.DictReader(io.StringIO(csv_content))
        headers = reader.fieldnames or []

        # Auto-detect format if not specified
        if format_type is None:
            format_type = self.detect_format(headers)

        if format_type is None or format_type not in self.FORMATS:
            return ImportResult(0, 1, [], [{'row': 0, 'error': 'Unknown CSV format'}])

        mapping = self.FORMATS[format_type]
        type_map = self.TYPE_MAPPINGS[format_type]

        for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is 1)
            try:
                # Extract and validate fields
                raw_type = row.get(mapping['type'], '').strip()
                txn_type = type_map.get(raw_type)

                if txn_type not in ('buy', 'sell'):
                    # Skip non-buy/sell transactions (transfers, rewards, etc.)
                    continue

                # Parse date
                date_str = row.get(mapping['date'], '').strip()
                txn_date = self._parse_date(date_str)

                # Parse numeric fields
                quantity = self._parse_decimal(row.get(mapping['quantity'], '0'))
                price = self._parse_decimal(row.get(mapping['price'], '0'))
                fees = Decimal('0')
                if mapping['fees'] and row.get(mapping['fees']):
                    fees = self._parse_decimal(row.get(mapping['fees'], '0'))

                # Get symbol
                symbol = row.get(mapping['symbol'], '').strip().upper()

                # Validate required fields
                if not symbol:
                    raise ValueError("Missing symbol")
                if quantity <= 0:
                    raise ValueError("Invalid quantity")
                if price <= 0:
                    raise ValueError("Invalid price")

                transactions.append({
                    'transaction_type': txn_type,
                    'symbol': symbol,
                    'quantity': quantity,
                    'price_per_unit': price,
                    'fees': fees,
                    'transaction_date': txn_date,
                    'notes': row.get(mapping.get('notes', ''), ''),
                    'import_source': format_type,
                })

            except Exception as e:
                errors.append({
                    'row': row_num,
                    'error': str(e),
                    'data': dict(row),
                })

        return ImportResult(
            success_count=len(transactions),
            error_count=len(errors),
            transactions=transactions,
            errors=errors
        )

    def _parse_date(self, date_str: str) -> datetime:
        """Parse date string in various formats."""
        formats = [
            '%Y-%m-%dT%H:%M:%SZ',      # ISO format
            '%Y-%m-%d %H:%M:%S',        # Standard datetime
            '%Y-%m-%d',                 # Date only
            '%m/%d/%Y',                 # US format
            '%m/%d/%Y %H:%M:%S',        # US format with time
            '%d/%m/%Y',                 # EU format
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        raise ValueError(f"Cannot parse date: {date_str}")

    def _parse_decimal(self, value: str) -> Decimal:
        """Parse string to Decimal, handling currency symbols."""
        if not value:
            return Decimal('0')

        # Remove currency symbols and commas
        cleaned = value.replace('$', '').replace(',', '').replace(' ', '').strip()

        # Handle parentheses for negative numbers
        if cleaned.startswith('(') and cleaned.endswith(')'):
            cleaned = '-' + cleaned[1:-1]

        return Decimal(cleaned)
```

### Portfolio Service

```python
# src/portfolio/portfolio_service.py
import uuid
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime

from database import get_database_manager
from .cost_basis import calculate_simple_average, CostBasisResult
from .csv_importer import CSVImporter, ImportResult
from data_providers.provider_factory import DataProviderFactory

class PortfolioService:
    """Main service for portfolio operations."""

    def __init__(self):
        self._db = None
        self.csv_importer = CSVImporter()

    @property
    def db(self):
        """Lazy database initialization."""
        if self._db is None:
            self._db = get_database_manager()
        return self._db

    # ==================== Portfolio CRUD ====================

    def create_portfolio(self, name: str = "My Portfolio", description: str = "") -> str:
        """Create a new portfolio. Returns portfolio_id."""
        portfolio_id = str(uuid.uuid4())
        self.db.create_portfolio(portfolio_id, name, description)
        return portfolio_id

    def get_portfolio(self, portfolio_id: str) -> Optional[Dict]:
        """Get portfolio by ID."""
        return self.db.get_portfolio(portfolio_id)

    def get_default_portfolio(self) -> Dict:
        """Get or create the default portfolio."""
        portfolios = self.db.list_portfolios()
        if portfolios:
            return portfolios[0]

        # Create default portfolio
        portfolio_id = self.create_portfolio()
        return self.get_portfolio(portfolio_id)

    # ==================== Holdings ====================

    def get_holdings(self, portfolio_id: str) -> List[Dict]:
        """Get all holdings for a portfolio with current prices."""
        holdings = self.db.get_holdings(portfolio_id)

        # Group by asset type for efficient price fetching
        stocks = [h for h in holdings if h['asset_type'] == 'stock']
        cryptos = [h for h in holdings if h['asset_type'] == 'crypto']

        # Fetch prices
        if stocks:
            stock_provider = DataProviderFactory.get_provider('stock')
            stock_prices = stock_provider.get_prices_batch([h['symbol'] for h in stocks])
            for h in stocks:
                h['current_price'] = stock_prices.get(h['symbol'], Decimal('0'))

        if cryptos:
            crypto_provider = DataProviderFactory.get_provider('crypto')
            crypto_prices = crypto_provider.get_prices_batch([h['symbol'] for h in cryptos])
            for h in cryptos:
                h['current_price'] = crypto_prices.get(h['symbol'], Decimal('0'))

        # Calculate market value and gains
        for h in holdings:
            h['market_value'] = h['total_quantity'] * h.get('current_price', Decimal('0'))
            h['unrealized_gain'] = h['market_value'] - h['total_cost_basis']
            h['unrealized_gain_pct'] = (
                (h['unrealized_gain'] / h['total_cost_basis'] * 100)
                if h['total_cost_basis'] > 0 else Decimal('0')
            )

        return holdings

    def get_holding(self, portfolio_id: str, symbol: str) -> Optional[Dict]:
        """Get a specific holding."""
        return self.db.get_holding(portfolio_id, symbol)

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
        Returns transaction_id.
        """
        # Auto-detect asset type if not provided
        if asset_type is None:
            asset_type = DataProviderFactory.detect_asset_type(symbol)

        symbol = symbol.upper().replace('CRYPTO:', '')

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

        # Recalculate holding
        self._recalculate_holding(holding_id)

        return transaction_id

    def get_transactions(self, holding_id: str) -> List[Dict]:
        """Get all transactions for a holding."""
        return self.db.get_transactions(holding_id)

    def delete_transaction(self, transaction_id: str) -> bool:
        """Delete a transaction and recalculate holding."""
        txn = self.db.get_transaction(transaction_id)
        if not txn:
            return False

        holding_id = txn['holding_id']
        self.db.delete_transaction(transaction_id)
        self._recalculate_holding(holding_id)
        return True

    def _recalculate_holding(self, holding_id: str):
        """Recalculate holding totals from transactions."""
        transactions = self.db.get_transactions(holding_id)

        if not transactions:
            # No transactions, zero out holding
            self.db.update_holding(holding_id, Decimal('0'), Decimal('0'), Decimal('0'))
            return

        result = calculate_simple_average(transactions)

        self.db.update_holding(
            holding_id=holding_id,
            total_quantity=result.total_quantity,
            average_cost=result.average_cost,
            total_cost_basis=result.total_cost_basis
        )

    # ==================== CSV Import ====================

    def import_csv(self, portfolio_id: str, csv_content: str, filename: str) -> ImportResult:
        """
        Import transactions from CSV.
        Returns ImportResult with success/error counts.
        """
        result = self.csv_importer.parse_csv(csv_content)

        # Add each transaction
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
            except Exception as e:
                result.error_count += 1
                result.success_count -= 1
                result.errors.append({
                    'row': 'import',
                    'error': str(e),
                    'data': txn
                })

        # Log import
        import_id = str(uuid.uuid4())
        self.db.log_csv_import(
            import_id=import_id,
            portfolio_id=portfolio_id,
            filename=filename,
            row_count=result.success_count + result.error_count,
            success_count=result.success_count,
            error_count=result.error_count,
            errors_json=result.errors
        )

        return result

    # ==================== Portfolio Summary ====================

    def get_portfolio_summary(self, portfolio_id: str) -> Dict:
        """Get portfolio summary with totals."""
        holdings = self.get_holdings(portfolio_id)

        total_cost_basis = sum(h['total_cost_basis'] for h in holdings)
        total_market_value = sum(h['market_value'] for h in holdings)
        total_unrealized_gain = total_market_value - total_cost_basis
        total_unrealized_gain_pct = (
            (total_unrealized_gain / total_cost_basis * 100)
            if total_cost_basis > 0 else Decimal('0')
        )

        # Allocation by asset type
        stock_value = sum(h['market_value'] for h in holdings if h['asset_type'] == 'stock')
        crypto_value = sum(h['market_value'] for h in holdings if h['asset_type'] == 'crypto')

        return {
            'portfolio_id': portfolio_id,
            'total_cost_basis': total_cost_basis,
            'total_market_value': total_market_value,
            'total_unrealized_gain': total_unrealized_gain,
            'total_unrealized_gain_pct': total_unrealized_gain_pct,
            'holdings_count': len(holdings),
            'stock_value': stock_value,
            'crypto_value': crypto_value,
            'stock_allocation_pct': (stock_value / total_market_value * 100) if total_market_value > 0 else Decimal('0'),
            'crypto_allocation_pct': (crypto_value / total_market_value * 100) if total_market_value > 0 else Decimal('0'),
            'holdings': holdings,
        }
```

### Files to Create
- `src/portfolio/__init__.py`
- `src/portfolio/cost_basis.py`
- `src/portfolio/csv_importer.py`
- `src/portfolio/portfolio_service.py`

---

## Phase 4: Flask Routes

### New Routes in `app.py`

```python
# Add to src/app.py

from portfolio.portfolio_service import PortfolioService

# Initialize portfolio service
portfolio_service = PortfolioService()

# ==================== Portfolio Routes ====================

@app.route('/portfolio')
def portfolio():
    """Portfolio dashboard."""
    portfolio = portfolio_service.get_default_portfolio()
    summary = portfolio_service.get_portfolio_summary(portfolio['portfolio_id'])

    return render_template('portfolio.html',
                           portfolio=portfolio,
                           summary=summary,
                           holdings=summary['holdings'])

@app.route('/portfolio/add', methods=['GET', 'POST'])
def add_transaction():
    """Add transaction form."""
    if request.method == 'POST':
        portfolio = portfolio_service.get_default_portfolio()

        try:
            portfolio_service.add_transaction(
                portfolio_id=portfolio['portfolio_id'],
                symbol=request.form['symbol'],
                transaction_type=request.form['transaction_type'],
                quantity=Decimal(request.form['quantity']),
                price_per_unit=Decimal(request.form['price']),
                transaction_date=datetime.strptime(request.form['date'], '%Y-%m-%d'),
                fees=Decimal(request.form.get('fees', '0') or '0'),
                notes=request.form.get('notes', ''),
                asset_type=request.form.get('asset_type'),
            )
            session['status_message'] = '✅ Transaction added successfully'
        except Exception as e:
            session['status_message'] = f'❌ Error: {str(e)}'

        return redirect(url_for('portfolio'))

    return render_template('add_transaction.html')

@app.route('/portfolio/import', methods=['GET', 'POST'])
def import_csv():
    """CSV import page."""
    if request.method == 'POST':
        portfolio = portfolio_service.get_default_portfolio()

        if 'csv_file' not in request.files:
            session['status_message'] = '⚠️ No file uploaded'
            return redirect(url_for('import_csv'))

        file = request.files['csv_file']
        if file.filename == '':
            session['status_message'] = '⚠️ No file selected'
            return redirect(url_for('import_csv'))

        try:
            csv_content = file.read().decode('utf-8')
            result = portfolio_service.import_csv(
                portfolio_id=portfolio['portfolio_id'],
                csv_content=csv_content,
                filename=file.filename
            )

            if result.error_count > 0:
                session['status_message'] = f'⚠️ Imported {result.success_count} transactions, {result.error_count} errors'
                session['import_errors'] = result.errors
            else:
                session['status_message'] = f'✅ Successfully imported {result.success_count} transactions'

        except Exception as e:
            session['status_message'] = f'❌ Import failed: {str(e)}'

        return redirect(url_for('portfolio'))

    return render_template('import_csv.html')

@app.route('/portfolio/holding/<symbol>')
def holding_detail(symbol: str):
    """View holding details and transactions."""
    portfolio = portfolio_service.get_default_portfolio()
    holding = portfolio_service.get_holding(portfolio['portfolio_id'], symbol)

    if not holding:
        session['status_message'] = f'⚠️ Holding not found: {symbol}'
        return redirect(url_for('portfolio'))

    transactions = portfolio_service.get_transactions(holding['holding_id'])

    # Get current price
    provider, _ = DataProviderFactory.get_provider_for_symbol(symbol)
    current_price = provider.get_current_price(symbol) or Decimal('0')

    holding['current_price'] = current_price
    holding['market_value'] = holding['total_quantity'] * current_price
    holding['unrealized_gain'] = holding['market_value'] - holding['total_cost_basis']

    return render_template('holding_detail.html',
                           holding=holding,
                           transactions=transactions)

@app.route('/portfolio/transaction/<transaction_id>/delete', methods=['POST'])
def delete_transaction(transaction_id: str):
    """Delete a transaction."""
    if portfolio_service.delete_transaction(transaction_id):
        session['status_message'] = '✅ Transaction deleted'
    else:
        session['status_message'] = '❌ Transaction not found'

    return redirect(request.referrer or url_for('portfolio'))
```

---

## Phase 5: Templates

### Portfolio Dashboard (`templates/portfolio.html`)

Key sections:
- Summary cards (total value, gain/loss, allocation)
- Holdings table with current prices
- Quick add transaction button
- CSV import button

### Add Transaction Form (`templates/add_transaction.html`)

Fields:
- Symbol (text input with auto-detect)
- Asset Type (radio: Stock / Crypto)
- Transaction Type (select: Buy / Sell)
- Quantity (number input, 8 decimal places)
- Price per Unit (number input)
- Fees (optional)
- Date (date picker)
- Notes (optional textarea)

### CSV Import (`templates/import_csv.html`)

- File upload area
- Format detection info
- Preview before import
- Error display

### Holding Detail (`templates/holding_detail.html`)

- Holding summary card
- Transaction history table
- Delete transaction buttons

---

## Phase 6: Testing

### Test Files to Create

```
test_cost_basis.py      # Unit tests for cost basis calculations
test_csv_importer.py    # CSV parsing tests with sample files
test_portfolio_service.py  # Integration tests
```

### Sample Test Cases

```python
# test_cost_basis.py
def test_simple_buy():
    """Single buy should set average cost equal to purchase price."""
    txns = [{'transaction_type': 'buy', 'quantity': 10, 'price_per_unit': 100, 'fees': 0, 'transaction_date': datetime.now()}]
    result = calculate_simple_average(txns)
    assert result.total_quantity == 10
    assert result.average_cost == 100
    assert result.total_cost_basis == 1000

def test_averaging_down():
    """Two buys at different prices should average."""
    txns = [
        {'transaction_type': 'buy', 'quantity': 10, 'price_per_unit': 100, 'fees': 0, 'transaction_date': datetime(2024, 1, 1)},
        {'transaction_type': 'buy', 'quantity': 10, 'price_per_unit': 50, 'fees': 0, 'transaction_date': datetime(2024, 1, 2)},
    ]
    result = calculate_simple_average(txns)
    assert result.total_quantity == 20
    assert result.average_cost == 75  # (1000 + 500) / 20
    assert result.total_cost_basis == 1500

def test_partial_sell():
    """Selling partial position should maintain average cost."""
    txns = [
        {'transaction_type': 'buy', 'quantity': 10, 'price_per_unit': 100, 'fees': 0, 'transaction_date': datetime(2024, 1, 1)},
        {'transaction_type': 'sell', 'quantity': 5, 'price_per_unit': 120, 'fees': 0, 'transaction_date': datetime(2024, 1, 2)},
    ]
    result = calculate_simple_average(txns)
    assert result.total_quantity == 5
    assert result.average_cost == 100  # Unchanged
    assert result.total_cost_basis == 500
    assert result.realized_gains == 100  # (5 * 120) - (5 * 100)
```

---

## Implementation Order

| Step | Task | Files | Estimated Complexity |
|------|------|-------|---------------------|
| 1 | Database schema | `src/database.py` | Medium |
| 2 | Cost basis calculator | `src/portfolio/cost_basis.py` | Low |
| 3 | CSV importer | `src/portfolio/csv_importer.py` | Medium |
| 4 | Data providers | `src/data_providers/*.py` | Medium |
| 5 | Portfolio service | `src/portfolio/portfolio_service.py` | High |
| 6 | Flask routes | `src/app.py` | Medium |
| 7 | Templates | `templates/portfolio*.html` | Medium |
| 8 | Tests | `test_*.py` | Low |

---

## Environment Variables (New)

```
# Add to .env
COINGECKO_API_KEY=optional_for_higher_limits
```

---

## Verification Plan

1. **Unit Tests**: Run `pytest test_cost_basis.py test_csv_importer.py`
2. **Manual Testing**:
   - Create portfolio
   - Add manual BTC buy transaction
   - Add manual AAPL buy transaction
   - Verify prices fetch correctly
   - Import sample Coinbase CSV
   - Verify cost basis calculations
   - Delete transaction and verify recalculation
3. **UI Testing**:
   - Navigate through all portfolio pages
   - Test form validation
   - Test error handling
