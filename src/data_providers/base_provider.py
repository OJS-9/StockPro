"""
Abstract base class for data providers.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional
from decimal import Decimal


class BaseDataProvider(ABC):
    """Abstract interface for price data providers."""

    @abstractmethod
    def get_current_price(self, symbol: str) -> Optional[Decimal]:
        """
        Get current price for a symbol.

        Args:
            symbol: Asset symbol (e.g., 'AAPL', 'BTC')

        Returns:
            Current price as Decimal, or None if unavailable
        """
        pass

    @abstractmethod
    def get_prices_batch(self, symbols: list) -> Dict[str, Decimal]:
        """
        Get current prices for multiple symbols.

        Args:
            symbols: List of asset symbols

        Returns:
            Dict mapping symbol to price
        """
        pass

    @abstractmethod
    def validate_symbol(self, symbol: str) -> bool:
        """
        Check if symbol is valid and data is available.

        Args:
            symbol: Asset symbol to validate

        Returns:
            True if symbol is valid, False otherwise
        """
        pass

    @abstractmethod
    def get_asset_info(self, symbol: str) -> Optional[Dict]:
        """
        Get basic info about an asset (name, market cap, etc.).

        Args:
            symbol: Asset symbol

        Returns:
            Dict with asset info, or None if unavailable
        """
        pass
