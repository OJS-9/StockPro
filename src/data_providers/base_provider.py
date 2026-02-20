"""
Abstract base class for data providers.
"""

import os
import time
from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple
from decimal import Decimal


class BaseDataProvider(ABC):
    """Abstract interface for price data providers."""

    # TTL in seconds, configurable via PRICE_CACHE_TTL_SECONDS env var (default 60)
    _CACHE_TTL: int = int(os.getenv('PRICE_CACHE_TTL_SECONDS', '60'))

    def __init__(self):
        # { symbol: (price, fetched_at) }
        self._price_cache: Dict[str, Tuple[Decimal, float]] = {}

    def _get_cached_price(self, symbol: str) -> Optional[Decimal]:
        """Return cached price if still within TTL, else None."""
        entry = self._price_cache.get(symbol.upper())
        if entry and (time.monotonic() - entry[1]) < self._CACHE_TTL:
            return entry[0]
        return None

    def _set_cached_price(self, symbol: str, price: Decimal):
        """Store a price in the cache with current timestamp."""
        self._price_cache[symbol.upper()] = (price, time.monotonic())

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
