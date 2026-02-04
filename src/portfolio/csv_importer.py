"""
CSV importer for transaction data from various sources.

Supports:
- Coinbase export format
- Robinhood export format
- Generic CSV format
"""

import csv
import io
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import List, Dict, Optional
from dataclasses import dataclass, field


@dataclass
class ImportResult:
    """Result of CSV import operation."""
    success_count: int
    error_count: int
    transactions: List[Dict] = field(default_factory=list)
    errors: List[Dict] = field(default_factory=list)


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
            'Buy': 'buy',
            'Sell': 'sell',
        }
    }

    def detect_format(self, headers: List[str]) -> Optional[str]:
        """
        Detect CSV format based on headers.

        Args:
            headers: List of column headers

        Returns:
            Format name ('coinbase', 'robinhood', 'generic') or None
        """
        headers_lower = [h.lower() for h in headers]

        # Check for Coinbase format
        if 'timestamp' in headers_lower and 'asset' in headers_lower:
            return 'coinbase'

        # Check for Robinhood format
        if 'activity date' in headers_lower and 'instrument' in headers_lower:
            return 'robinhood'

        # Check for generic format
        if 'date' in headers_lower and 'symbol' in headers_lower:
            return 'generic'

        return None

    def parse_csv(
        self,
        csv_content: str,
        format_type: Optional[str] = None
    ) -> ImportResult:
        """
        Parse CSV content into transactions.

        Args:
            csv_content: Raw CSV string content
            format_type: Optional format override ('coinbase', 'robinhood', 'generic')
                        If not provided, format will be auto-detected

        Returns:
            ImportResult with parsed transactions and any errors
        """
        transactions = []
        errors = []

        try:
            reader = csv.DictReader(io.StringIO(csv_content))
            headers = reader.fieldnames or []
        except Exception as e:
            return ImportResult(0, 1, [], [{'row': 0, 'error': f'Failed to parse CSV: {e}'}])

        # Auto-detect format if not specified
        if format_type is None:
            format_type = self.detect_format(headers)

        if format_type is None or format_type not in self.FORMATS:
            return ImportResult(
                0, 1, [],
                [{'row': 0, 'error': 'Unknown CSV format. Expected columns: date, symbol, type, quantity, price'}]
            )

        mapping = self.FORMATS[format_type]
        type_map = self.TYPE_MAPPINGS[format_type]

        for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
            try:
                # Extract and validate transaction type
                raw_type = row.get(mapping['type'], '').strip()
                txn_type = type_map.get(raw_type)

                if txn_type not in ('buy', 'sell'):
                    # Skip non-buy/sell transactions (transfers, rewards, staking, etc.)
                    continue

                # Parse date
                date_str = row.get(mapping['date'], '').strip()
                if not date_str:
                    raise ValueError("Missing date")
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
                    raise ValueError(f"Invalid quantity: {quantity}")
                if price <= 0:
                    raise ValueError(f"Invalid price: {price}")

                transactions.append({
                    'transaction_type': txn_type,
                    'symbol': symbol,
                    'quantity': quantity,
                    'price_per_unit': price,
                    'fees': fees,
                    'transaction_date': txn_date,
                    'notes': row.get(mapping.get('notes', ''), '') or '',
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
        """
        Parse date string in various formats.

        Supported formats:
        - ISO: 2024-01-15T10:30:00Z
        - Standard: 2024-01-15 10:30:00
        - Date only: 2024-01-15
        - US format: 01/15/2024, 01/15/2024 10:30:00
        - EU format: 15/01/2024

        Args:
            date_str: Date string to parse

        Returns:
            datetime object

        Raises:
            ValueError: If date cannot be parsed
        """
        formats = [
            '%Y-%m-%dT%H:%M:%SZ',       # ISO format with Z
            '%Y-%m-%dT%H:%M:%S',        # ISO format without Z
            '%Y-%m-%d %H:%M:%S',        # Standard datetime
            '%Y-%m-%d',                 # Date only
            '%m/%d/%Y %H:%M:%S',        # US format with time
            '%m/%d/%Y',                 # US format
            '%d/%m/%Y %H:%M:%S',        # EU format with time
            '%d/%m/%Y',                 # EU format
            '%Y/%m/%d',                 # Alternative format
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue

        raise ValueError(f"Cannot parse date: {date_str}")

    def _parse_decimal(self, value: str) -> Decimal:
        """
        Parse string to Decimal, handling currency symbols and formatting.

        Handles:
        - Currency symbols: $100.00 -> 100.00
        - Commas: 1,000.00 -> 1000.00
        - Parentheses for negatives: (100) -> -100
        - Whitespace

        Args:
            value: String value to parse

        Returns:
            Decimal value

        Raises:
            InvalidOperation: If value cannot be parsed
        """
        if not value:
            return Decimal('0')

        # Remove currency symbols, commas, and whitespace
        cleaned = value.replace('$', '').replace(',', '').replace(' ', '').strip()

        # Handle parentheses for negative numbers (accounting format)
        if cleaned.startswith('(') and cleaned.endswith(')'):
            cleaned = '-' + cleaned[1:-1]

        # Handle empty after cleaning
        if not cleaned:
            return Decimal('0')

        return Decimal(cleaned)

    def preview_csv(self, csv_content: str, max_rows: int = 5) -> Dict:
        """
        Preview CSV content without fully parsing.

        Args:
            csv_content: Raw CSV string
            max_rows: Maximum rows to preview

        Returns:
            Dict with format, headers, and sample rows
        """
        try:
            reader = csv.DictReader(io.StringIO(csv_content))
            headers = reader.fieldnames or []
            format_type = self.detect_format(headers)

            rows = []
            for i, row in enumerate(reader):
                if i >= max_rows:
                    break
                rows.append(dict(row))

            return {
                'format': format_type,
                'headers': headers,
                'sample_rows': rows,
                'format_detected': format_type is not None
            }

        except Exception as e:
            return {
                'format': None,
                'headers': [],
                'sample_rows': [],
                'format_detected': False,
                'error': str(e)
            }
