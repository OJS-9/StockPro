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
        super().__init__()
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
        Get current stock price from Alpha Vantage GLOBAL_QUOTE.

        Uses GLOBAL_QUOTE for real-time price data, with fallback to
        COMPANY_OVERVIEW's 50DayMovingAverage if GLOBAL_QUOTE fails.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Current price as Decimal, or None if unavailable
        """
        # Return cached price if still fresh
        cached = self._get_cached_price(symbol)
        if cached is not None:
            return cached

        # Try GLOBAL_QUOTE first (real-time price)
        try:
            result = self.mcp_manager.get_global_quote(symbol)

            # Check for rate limit or error messages
            if isinstance(result, dict):
                if 'Note' in result or 'Information' in result or 'Error Message' in result:
                    print(f"Alpha Vantage API message for {symbol}: {result.get('Note') or result.get('Information') or result.get('Error Message')}")

            # Handle CSV response format from Alpha Vantage MCP
            # Response: {"raw": "symbol,open,high,low,price,...\r\nAAPL,272.28,...\r\n"}
            if 'raw' in result:
                csv_data = result['raw']
                lines = csv_data.strip().split('\n')
                if len(lines) >= 2:
                    headers = [h.strip() for h in lines[0].split(',')]
                    values = [v.strip() for v in lines[1].split(',')]

                    if 'price' in headers:
                        price_idx = headers.index('price')
                        price_str = values[price_idx].replace('%', '')
                        if price_str:
                            price = Decimal(price_str)
                            self._set_cached_price(symbol, price)
                            return price

            # Handle JSON response format (legacy/fallback)
            # GLOBAL_QUOTE returns data in "Global Quote" key
            quote = result.get('Global Quote', result)
            price_str = quote.get('05. price') or quote.get('price')
            if price_str:
                price = Decimal(str(price_str))
                self._set_cached_price(symbol, price)
                return price

        except Exception as e:
            print(f"GLOBAL_QUOTE failed for {symbol}: {e}")

        # Fallback to OVERVIEW with 50DayMovingAverage
        try:
            result = self.mcp_manager.get_company_overview(symbol)

            if '50DayMovingAverage' in result and result['50DayMovingAverage']:
                price = Decimal(str(result['50DayMovingAverage']))
                self._set_cached_price(symbol, price)
                return price

            # Try calculating from market cap as last resort
            if 'MarketCapitalization' in result and 'SharesOutstanding' in result:
                market_cap = result.get('MarketCapitalization')
                shares = result.get('SharesOutstanding')
                if market_cap and shares:
                    market_cap = Decimal(str(market_cap))
                    shares = Decimal(str(shares))
                    if shares > 0:
                        price = market_cap / shares
                        self._set_cached_price(symbol, price)
                        return price

        except Exception as e:
            print(f"OVERVIEW fallback failed for {symbol}: {e}")

        return None

    def get_price_with_change(self, symbol: str) -> dict:
        """
        Get current price and 24h change% from Alpha Vantage GLOBAL_QUOTE.

        Returns:
            {'price': Decimal|None, 'change_percent': Decimal|None}
        """
        result = {'price': None, 'change_percent': None}
        try:
            raw = self.mcp_manager.get_global_quote(symbol)
            if 'raw' in raw:
                lines = raw['raw'].strip().split('\n')
                if len(lines) >= 2:
                    headers = [h.strip() for h in lines[0].split(',')]
                    values = [v.strip() for v in lines[1].split(',')]
                    row = dict(zip(headers, values))
                    price_str = row.get('price', '').replace('%', '')
                    change_str = row.get('changePercent', '').replace('%', '')
                    if price_str:
                        result['price'] = Decimal(price_str)
                        self._set_cached_price(symbol, result['price'])
                    if change_str:
                        result['change_percent'] = Decimal(change_str)
            else:
                quote = raw.get('Global Quote', raw)
                price_str = (quote.get('05. price') or quote.get('price') or '').replace('%', '')
                change_str = (quote.get('10. change percent') or quote.get('change percent') or '').replace('%', '')
                if price_str:
                    result['price'] = Decimal(str(price_str))
                    self._set_cached_price(symbol, result['price'])
                if change_str:
                    result['change_percent'] = Decimal(str(change_str))
        except Exception as e:
            print(f"get_price_with_change failed for {symbol}: {e}")
        return result

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
