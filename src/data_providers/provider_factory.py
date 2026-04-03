"""
Factory for data providers with asset type detection.
"""

from typing import Tuple

from .base_provider import BaseDataProvider
from .stock_provider import StockDataProvider
from .crypto_provider import CryptoDataProvider


class DataProviderFactory:
    """Factory to get appropriate data provider based on asset type."""

    _stock_provider = None
    _crypto_provider = None

    # Known crypto symbols for quick detection
    CRYPTO_SYMBOLS = {
        # Major coins
        "BTC",
        "ETH",
        "SOL",
        "ADA",
        "DOT",
        "MATIC",
        "AVAX",
        "LINK",
        "UNI",
        "ATOM",
        "XRP",
        "DOGE",
        "SHIB",
        "LTC",
        "BCH",
        "XLM",
        "ALGO",
        "VET",
        "FIL",
        "AAVE",
        "MKR",
        # Layer 2s and newer chains
        "NEAR",
        "APT",
        "ARB",
        "OP",
        "SUI",
        "SEI",
        "INJ",
        "TIA",
        # Memecoins
        "PEPE",
        "WIF",
        "BONK",
        "FLOKI",
        "MEME",
        # DeFi
        "CRV",
        "COMP",
        "SNX",
        "YFI",
        "SUSHI",
        "BAL",
        # Stablecoins (for reference, though typically not tracked)
        "USDT",
        "USDC",
        "DAI",
        "BUSD",
        "TUSD",
    }

    @classmethod
    def get_provider(cls, asset_type: str) -> BaseDataProvider:
        """
        Get provider for specified asset type.

        Args:
            asset_type: 'stock' or 'crypto'

        Returns:
            Appropriate data provider instance
        """
        if asset_type == "crypto":
            if cls._crypto_provider is None:
                cls._crypto_provider = CryptoDataProvider()
            return cls._crypto_provider
        else:
            if cls._stock_provider is None:
                cls._stock_provider = StockDataProvider()
            return cls._stock_provider

    @classmethod
    def detect_asset_type(cls, symbol: str) -> str:
        """
        Auto-detect if symbol is stock or crypto.

        Detection logic:
        1. Check for CRYPTO: prefix (explicit)
        2. Check against known crypto symbols list
        3. Default to stock

        Args:
            symbol: Asset symbol

        Returns:
            'stock' or 'crypto'
        """
        symbol_upper = symbol.upper().strip()

        # Check for explicit CRYPTO: prefix
        if symbol_upper.startswith("CRYPTO:"):
            return "crypto"

        # Remove any prefix for lookup
        clean_symbol = symbol_upper.replace("CRYPTO:", "")

        # Check known crypto symbols
        if clean_symbol in cls.CRYPTO_SYMBOLS:
            return "crypto"

        # Default to stock
        return "stock"

    @classmethod
    def get_provider_for_symbol(cls, symbol: str) -> Tuple[BaseDataProvider, str]:
        """
        Get provider and detected asset type for a symbol.

        Args:
            symbol: Asset symbol

        Returns:
            Tuple of (provider, asset_type)
        """
        asset_type = cls.detect_asset_type(symbol)
        provider = cls.get_provider(asset_type)
        return provider, asset_type

    @classmethod
    def is_crypto(cls, symbol: str) -> bool:
        """
        Check if symbol is a cryptocurrency.

        Args:
            symbol: Asset symbol

        Returns:
            True if crypto, False otherwise
        """
        return cls.detect_asset_type(symbol) == "crypto"

    @classmethod
    def is_stock(cls, symbol: str) -> bool:
        """
        Check if symbol is a stock.

        Args:
            symbol: Asset symbol

        Returns:
            True if stock, False otherwise
        """
        return cls.detect_asset_type(symbol) == "stock"

    @classmethod
    def add_crypto_symbol(cls, symbol: str):
        """
        Add a symbol to the known crypto list.

        Useful for adding new or less common crypto symbols.

        Args:
            symbol: Crypto symbol to add
        """
        cls.CRYPTO_SYMBOLS.add(symbol.upper())
