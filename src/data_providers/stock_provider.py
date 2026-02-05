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
        Get current stock price from Alpha Vantage GLOBAL_QUOTE.

        Uses GLOBAL_QUOTE for real-time price data, with fallback to
        COMPANY_OVERVIEW's 50DayMovingAverage if GLOBAL_QUOTE fails.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Current price as Decimal, or None if unavailable
        """
        # #region agent log
        log_path = '/Users/orsalinas/.claude-worktrees/Stock Protfolio Agent/clever-poitras/.cursor/debug.log'
        import json as _json
        from datetime import datetime as _dt
        def _log(hyp, loc, msg, data):
            try:
                with open(log_path, 'a') as f:
                    f.write(_json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":hyp,"location":loc,"message":msg,"data":data,"timestamp":int(_dt.now().timestamp()*1000)})+'\n')
            except: pass
        # #endregion
        
        _log("A", "stock_provider:get_current_price:entry", "Starting price fetch", {"symbol": symbol})
        
        # Try GLOBAL_QUOTE first (real-time price)
        try:
            result = self.mcp_manager.get_global_quote(symbol)
            
            # #region agent log
            _log("B", "stock_provider:get_current_price:global_quote_response", "GLOBAL_QUOTE raw response", {"symbol": symbol, "result_keys": list(result.keys()) if isinstance(result, dict) else str(type(result)), "result_preview": str(result)[:500]})
            # #endregion
            
            # Check for rate limit or error messages
            if isinstance(result, dict):
                if 'Note' in result:
                    _log("D", "stock_provider:get_current_price:rate_limit", "API rate limit detected", {"symbol": symbol, "note": result.get('Note', '')[:200]})
                if 'Information' in result:
                    _log("D", "stock_provider:get_current_price:api_info", "API information message", {"symbol": symbol, "info": result.get('Information', '')[:200]})
                if 'Error Message' in result:
                    _log("D", "stock_provider:get_current_price:api_error", "API error message", {"symbol": symbol, "error": result.get('Error Message', '')[:200]})

            # Handle CSV response format from Alpha Vantage MCP
            # Response: {"raw": "symbol,open,high,low,price,...\r\nAAPL,272.28,...\r\n"}
            if 'raw' in result:
                csv_data = result['raw']
                lines = csv_data.strip().split('\n')
                _log("B", "stock_provider:get_current_price:csv_parsing", "Parsing CSV response", {"symbol": symbol, "line_count": len(lines), "headers": lines[0] if lines else "EMPTY"})
                if len(lines) >= 2:
                    headers = [h.strip() for h in lines[0].split(',')]
                    values = [v.strip() for v in lines[1].split(',')]
                    
                    # Find price column
                    if 'price' in headers:
                        price_idx = headers.index('price')
                        price_str = values[price_idx].replace('%', '')
                        if price_str:
                            price = Decimal(price_str)
                            _log("A", "stock_provider:get_current_price:csv_success", "Price extracted from CSV", {"symbol": symbol, "price": str(price)})
                            return price
                        else:
                            _log("B", "stock_provider:get_current_price:csv_empty_price", "CSV price column empty", {"symbol": symbol, "values": values})
                    else:
                        _log("B", "stock_provider:get_current_price:csv_no_price_col", "No price column in CSV", {"symbol": symbol, "headers": headers})

            # Handle JSON response format (legacy/fallback)
            # GLOBAL_QUOTE returns data in "Global Quote" key
            quote = result.get('Global Quote', result)
            _log("B", "stock_provider:get_current_price:json_parsing", "Parsing JSON response", {"symbol": symbol, "quote_keys": list(quote.keys()) if isinstance(quote, dict) else str(type(quote))})

            # Price is in "05. price" field
            price_str = quote.get('05. price') or quote.get('price')
            if price_str:
                price = Decimal(str(price_str))
                _log("A", "stock_provider:get_current_price:json_success", "Price extracted from JSON", {"symbol": symbol, "price": str(price)})
                return price
            else:
                _log("B", "stock_provider:get_current_price:json_no_price", "No price in JSON response", {"symbol": symbol, "quote": str(quote)[:300]})

        except Exception as e:
            _log("E", "stock_provider:get_current_price:global_quote_exception", "GLOBAL_QUOTE exception", {"symbol": symbol, "error": str(e), "error_type": type(e).__name__})
            print(f"GLOBAL_QUOTE failed for {symbol}: {e}")

        # Fallback to OVERVIEW with 50DayMovingAverage
        _log("A", "stock_provider:get_current_price:fallback_start", "Trying OVERVIEW fallback", {"symbol": symbol})
        try:
            result = self.mcp_manager.get_company_overview(symbol)
            _log("B", "stock_provider:get_current_price:overview_response", "OVERVIEW raw response", {"symbol": symbol, "result_keys": list(result.keys()) if isinstance(result, dict) else str(type(result)), "has_50dma": '50DayMovingAverage' in result if isinstance(result, dict) else False})

            if '50DayMovingAverage' in result and result['50DayMovingAverage']:
                price = Decimal(str(result['50DayMovingAverage']))
                _log("A", "stock_provider:get_current_price:overview_success", "Price from 50DMA", {"symbol": symbol, "price": str(price)})
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
                        _log("A", "stock_provider:get_current_price:marketcap_success", "Price from market cap", {"symbol": symbol, "price": str(price)})
                        return price

            _log("B", "stock_provider:get_current_price:overview_no_data", "OVERVIEW has no usable price data", {"symbol": symbol})

        except Exception as e:
            _log("E", "stock_provider:get_current_price:overview_exception", "OVERVIEW fallback exception", {"symbol": symbol, "error": str(e), "error_type": type(e).__name__})
            print(f"OVERVIEW fallback failed for {symbol}: {e}")

        _log("A", "stock_provider:get_current_price:return_none", "Returning None - all methods failed", {"symbol": symbol})
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
        # #region agent log
        log_path = '/Users/orsalinas/.claude-worktrees/Stock Protfolio Agent/clever-poitras/.cursor/debug.log'
        import json as _json
        from datetime import datetime as _dt
        def _log(hyp, loc, msg, data):
            try:
                with open(log_path, 'a') as f:
                    f.write(_json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":hyp,"location":loc,"message":msg,"data":data,"timestamp":int(_dt.now().timestamp()*1000)})+'\n')
            except: pass
        # #endregion
        
        _log("C", "stock_provider:get_prices_batch:entry", "Batch fetch starting", {"symbols": symbols, "count": len(symbols)})
        prices = {}
        for symbol in symbols:
            price = self.get_current_price(symbol)
            _log("C", "stock_provider:get_prices_batch:after_fetch", "Price result for symbol", {"symbol": symbol, "price": str(price) if price else None, "is_none": price is None})
            if price is not None:
                prices[symbol.upper()] = price
        _log("C", "stock_provider:get_prices_batch:return", "Batch fetch complete", {"requested": symbols, "returned": list(prices.keys()), "missing": [s for s in symbols if s.upper() not in prices]})
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
