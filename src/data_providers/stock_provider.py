"""
Stock data provider using Alpha Vantage MCP.
"""

import os
import sys
from decimal import Decimal
from typing import Dict, Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .base_provider import BaseDataProvider


class StockDataProvider(BaseDataProvider):
    """Stock data provider using Alpha Vantage MCP."""

    def __init__(self):
        """Initialize stock data provider."""
        self._mcp_manager = None

    @property
    def mcp_manager(self):
        """Lazy-load MCP manager."""
        if self._mcp_manager is None:
            from mcp_manager import get_mcp_manager
            self._mcp_manager = get_mcp_manager()
        return self._mcp_manager

    def get_current_price(self, symbol: str) -> Optional[Decimal]:
        """
        Get current stock price from Alpha Vantage OVERVIEW tool.

        Note: OVERVIEW returns fundamental data, not real-time price.
        For real-time quotes, you would need the GLOBAL_QUOTE endpoint.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Current price as Decimal, or None if unavailable
        """
        try:
            result = self.mcp_manager.get_company_overview(symbol)

            # Try to get price from various possible fields
            price = None

            # Alpha Vantage OVERVIEW doesn't include real-time price
            # It includes 52WeekHigh, 52WeekLow, 50DayMovingAverage, etc.
            # For portfolio tracking, we'll use 50DayMovingAverage as an approximation
            # In production, you'd want to add GLOBAL_QUOTE support

            if '50DayMovingAverage' in result:
                price = result['50DayMovingAverage']
            elif 'MarketCapitalization' in result and 'SharesOutstanding' in result:
                # Calculate from market cap if available
                market_cap = Decimal(str(result['MarketCapitalization']))
                shares = Decimal(str(result['SharesOutstanding']))
                if shares > 0:
                    price = market_cap / shares

            if price:
                return Decimal(str(price))

            return None

        except Exception as e:
            print(f"Error fetching stock price for {symbol}: {e}")
            return None

    def get_prices_batch(self, symbols: list) -> Dict[str, Decimal]:
        """
        Get prices for multiple stocks.

        Due to Alpha Vantage API rate limits, this fetches sequentially.

        Args:
            symbols: List of stock ticker symbols

        Returns:
            Dict mapping symbol to price
        """
        prices = {}
        for symbol in symbols:
            price = self.get_current_price(symbol)
            if price is not None:
                prices[symbol.upper()] = price
        return prices

    def validate_symbol(self, symbol: str) -> bool:
        """
        Check if stock ticker is valid.

        Args:
            symbol: Stock ticker symbol

        Returns:
            True if valid, False otherwise
        """
        try:
            result = self.mcp_manager.get_company_overview(symbol)
            # Check if we got valid data back
            return bool(result and result.get('Symbol'))
        except Exception:
            return False

    def get_asset_info(self, symbol: str) -> Optional[Dict]:
        """
        Get company overview information.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Dict with company info, or None if unavailable
        """
        try:
            result = self.mcp_manager.get_company_overview(symbol)

            if not result or 'Symbol' not in result:
                return None

            return {
                'symbol': result.get('Symbol', '').upper(),
                'name': result.get('Name', ''),
                'description': result.get('Description', ''),
                'exchange': result.get('Exchange', ''),
                'sector': result.get('Sector', ''),
                'industry': result.get('Industry', ''),
                'market_cap': result.get('MarketCapitalization'),
                'pe_ratio': result.get('PERatio'),
                'dividend_yield': result.get('DividendYield'),
                '52_week_high': result.get('52WeekHigh'),
                '52_week_low': result.get('52WeekLow'),
                '50_day_ma': result.get('50DayMovingAverage'),
                '200_day_ma': result.get('200DayMovingAverage'),
            }

        except Exception as e:
            print(f"Error fetching asset info for {symbol}: {e}")
            return None
