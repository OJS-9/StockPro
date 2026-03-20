"""
Stock data provider using Alpha Vantage MCP.
"""

import os
import sys
import time
from decimal import Decimal
from typing import Any, Dict, Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .base_provider import BaseDataProvider


MARKETWATCH_NIMBLE_AGENT_ID = os.getenv(
    "NIMBLE_MARKETWATCH_INFO_AGENT_ID",
    "marketwatch_info_2026_02_23_zpwkys0h_3859835d",
)
SEEKINGALPHA_NIMBLE_AGENT_ID = os.getenv(
    "NIMBLE_SEEKINGALPHA_AGENT_ID",
    "seekingalpha_stock_symbol_2026_03_19_ar32nvos",
)
NIMBLE_WARMUP_TIMEOUT_SECONDS = float(os.getenv("NIMBLE_WARMUP_TIMEOUT_SECONDS", "120"))

PRICE_FETCH_DEBUG = os.getenv("PRICE_FETCH_DEBUG", "0").lower() in {"1", "true", "yes", "on"}


class StockDataProvider(BaseDataProvider):
    """Stock data provider using Alpha Vantage MCP."""

    def __init__(self):
        """Initialize stock data provider."""
        super().__init__()
        self._mcp_manager = None
        self._nimble_client = None
        # { symbol: (change_percent, fetched_at) } — mirrors _price_cache TTL
        self._change_cache: dict = {}

    def _get_cached_change_percent(self, symbol: str) -> Optional[Decimal]:
        entry = self._change_cache.get(symbol.upper())
        if entry and (time.monotonic() - entry[1]) < self._CACHE_TTL:
            return entry[0]
        return None

    def _set_cached_change_percent(self, symbol: str, change_percent: Decimal):
        self._change_cache[symbol.upper()] = (change_percent, time.monotonic())

    @property
    def mcp_manager(self):
        """Lazy-load MCP manager."""
        if self._mcp_manager is None:
            from mcp_manager import get_mcp_manager
            self._mcp_manager = get_mcp_manager()
        return self._mcp_manager

    @property
    def nimble_client(self):
        """Lazy-load Nimble SDK client (optional)."""
        if self._nimble_client is not None:
            return self._nimble_client
        try:
            from nimble_client import NimbleClient

            self._nimble_client = NimbleClient()
        except Exception:
            # If Nimble isn't configured, keep going with Alpha Vantage.
            self._nimble_client = None
        return self._nimble_client

    def _parse_decimal(self, value: Any) -> Optional[Decimal]:
        """Parse a numeric-ish Nimble field into Decimal."""
        if value is None:
            return None
        if isinstance(value, (int, float, Decimal)):
            return Decimal(str(value))

        s = str(value).strip()
        if not s:
            return None

        # Common formatting: "$1,234.56", "+12.3%", "-0.4 %"
        s = s.replace("$", "").replace(",", "")
        s = s.replace("%", "")
        s = s.strip()

        try:
            return Decimal(s)
        except Exception:
            return None

    def _get_price_with_change_from_nimble(self, symbol: str) -> dict:
        """
        Nimble-first lookup for current price (+ optional change%).

        Returns:
            {'price': Decimal|None, 'change_percent': Decimal|None}
        """
        result = {"price": None, "change_percent": None}

        client = self.nimble_client
        if not client:
            return result

        try:
            # Your Nimble agent expects `ticker` as input (per provided schema screenshot).
            parsed_list = client.run_agent(
                MARKETWATCH_NIMBLE_AGENT_ID,
                {"ticker": symbol.upper()},
            )
            if not parsed_list:
                return result

            item: Any = parsed_list[0] if isinstance(parsed_list, list) else parsed_list
            if not isinstance(item, dict):
                return result

            result["price"] = self._parse_decimal(item.get("price"))

            # Agent output key is `change` in your schema screenshot.
            # Nimble sometimes returns percent without a trailing '%', so we parse as-is.
            change_raw = item.get("change")
            if change_raw is not None:
                result["change_percent"] = self._parse_decimal(change_raw)

            if PRICE_FETCH_DEBUG and result.get("price") is not None:
                print(
                    f"[price_debug] nimble hit for {symbol.upper()} "
                    f"(price={result.get('price')}, change_percent={result.get('change_percent')})"
                )
            return result
        except Exception:
            if PRICE_FETCH_DEBUG:
                print(f"[price_debug] nimble miss for {symbol.upper()}")
            return result

    def _get_price_from_seekingalpha(self, symbol: str) -> dict:
        """SeekingAlpha Nimble agent price lookup."""
        result = {"price": None, "change_percent": None}
        client = self.nimble_client
        if not client:
            return result
        try:
            parsed_list = client.run_agent(
                SEEKINGALPHA_NIMBLE_AGENT_ID,
                {"ticker": symbol.upper()},
            )
            if not parsed_list:
                return result
            item = parsed_list[0] if isinstance(parsed_list, list) else parsed_list
            if not isinstance(item, dict):
                return result
            result["price"] = self._parse_decimal(item.get("current_price"))
            result["change_percent"] = self._parse_decimal(item.get("price_change_percent"))
            if PRICE_FETCH_DEBUG and result.get("price") is not None:
                print(
                    f"[price_debug] seekingalpha hit for {symbol.upper()} "
                    f"(price={result.get('price')}, change_percent={result.get('change_percent')})"
                )
            return result
        except Exception:
            if PRICE_FETCH_DEBUG:
                print(f"[price_debug] seekingalpha miss for {symbol.upper()}")
            return result

    def _get_price_from_alpha_vantage(self, symbol: str) -> dict:
        """Alpha Vantage GLOBAL_QUOTE lookup (no cache read/write — caller handles caching)."""
        result = {"price": None, "change_percent": None}
        try:
            raw = self.mcp_manager.get_global_quote(symbol)
            if isinstance(raw, dict):
                if 'Note' in raw or 'Information' in raw or 'Error Message' in raw:
                    return result
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
                    if change_str:
                        result['change_percent'] = Decimal(change_str)
            else:
                quote = raw.get('Global Quote', raw)
                price_str = (quote.get('05. price') or quote.get('price') or '').replace('%', '')
                change_str = (quote.get('10. change percent') or quote.get('change percent') or '').replace('%', '')
                if price_str:
                    result['price'] = Decimal(str(price_str))
                if change_str:
                    result['change_percent'] = Decimal(str(change_str))
        except Exception as e:
            if PRICE_FETCH_DEBUG:
                print(f"[price_debug] alpha vantage miss for {symbol.upper()}: {e}")
        return result

    def _fetch_price_nimble_with_av_fallback(self, symbol: str) -> dict:
        """
        Fire both Nimble agents concurrently. If neither returns a valid price
        within NIMBLE_WARMUP_TIMEOUT_SECONDS, fall back to Alpha Vantage.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        client = self.nimble_client
        if not client:
            return self._get_price_from_alpha_vantage(symbol)

        nimble_fns = [
            self._get_price_with_change_from_nimble,   # MarketWatch
            self._get_price_from_seekingalpha,          # SeekingAlpha
        ]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {pool.submit(fn, symbol): fn.__name__ for fn in nimble_fns}
            try:
                for fut in as_completed(futures, timeout=NIMBLE_WARMUP_TIMEOUT_SECONDS):
                    result = fut.result()
                    if result.get("price") is not None:
                        if PRICE_FETCH_DEBUG:
                            print(f"[price_debug] warmup nimble hit {symbol.upper()} via {futures[fut]}")
                        return result
            except TimeoutError:
                if PRICE_FETCH_DEBUG:
                    print(f"[price_debug] warmup nimble timeout for {symbol.upper()}, falling back to AV")

        if PRICE_FETCH_DEBUG:
            print(f"[price_debug] warmup nimble miss for {symbol.upper()}, falling back to AV")
        return self._get_price_from_alpha_vantage(symbol)

    def get_prices_batch_warmup(self, symbols: list) -> dict:
        """
        Warmup-optimised batch fetch. All symbols fire simultaneously —
        each fires both Nimble agents concurrently, with AV as last resort.
        Symbols with a fresh cache entry are skipped.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if not symbols:
            return {}

        stale = [s for s in symbols if self._get_cached_price(s) is None]
        if not stale:
            return {}

        prices = {}
        with ThreadPoolExecutor(max_workers=len(stale)) as pool:
            futures = {pool.submit(self._fetch_price_nimble_with_av_fallback, sym): sym for sym in stale}
            for fut in as_completed(futures):
                sym = futures[fut]
                data = fut.result()
                if data.get("price") is not None:
                    prices[sym.upper()] = data["price"]
                    self._set_cached_price(sym, data["price"])
        return prices

    def get_current_price(self, symbol: str) -> Optional[Decimal]:
        """
        Get current stock price, preferring Nimble (MarketWatch agent) then Alpha Vantage.

        Uses Alpha Vantage for real-time price data, with fallback to
        COMPANY_OVERVIEW's 50DayMovingAverage if needed.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Current price as Decimal, or None if unavailable
        """
        # Return cached price if still fresh
        cached = self._get_cached_price(symbol)
        if cached is not None:
            return cached

        # Prefer Nimble (MarketWatch agent) if configured.
        nimble_data = self._get_price_with_change_from_nimble(symbol)
        if nimble_data.get("price") is not None:
            if PRICE_FETCH_DEBUG:
                print(f"[price_debug] get_current_price using nimble for {symbol.upper()}")
            self._set_cached_price(symbol, nimble_data["price"])
            return nimble_data["price"]

        # Try GLOBAL_QUOTE first (real-time price)
        try:
            result = self.mcp_manager.get_global_quote(symbol)

            # Check for rate limit or error messages
            if isinstance(result, dict):
                if 'Note' in result or 'Information' in result:
                    print(f"Alpha Vantage rate limit hit for {symbol}: {result.get('Note') or result.get('Information')}")
                    return None
                if 'Error Message' in result:
                    print(f"Alpha Vantage error for {symbol}: {result.get('Error Message')}")
                    return None

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

    # Minimum seconds between API calls (free tier: 5 req/min = 12s apart)
    _BATCH_DELAY: float = float(os.getenv('ALPHA_VANTAGE_BATCH_DELAY_SECONDS', '12'))

    def get_price_with_change(self, symbol: str) -> dict:
        """
        Get current price and change% (preferring Nimble, falling back to Alpha Vantage).

        Returns:
            {'price': Decimal|None, 'change_percent': Decimal|None}
        """
        # Full cache hit — skip all API calls
        cached_price = self._get_cached_price(symbol)
        cached_change = self._get_cached_change_percent(symbol)
        if cached_price is not None and cached_change is not None:
            if PRICE_FETCH_DEBUG:
                print(f"[price_debug] get_price_with_change full cache hit for {symbol.upper()}")
            return {"price": cached_price, "change_percent": cached_change}

        result = {"price": None, "change_percent": None}

        # Nimble-first: returns both price and change_percent for most symbols
        nimble_data = self._get_price_with_change_from_nimble(symbol)
        if nimble_data.get("price") is not None:
            self._set_cached_price(symbol, nimble_data["price"])
            result = nimble_data
            if result.get("change_percent") is not None:
                self._set_cached_change_percent(symbol, result["change_percent"])
                if PRICE_FETCH_DEBUG:
                    print(f"[price_debug] final source=nimble for {symbol.upper()} result={result}")
                return result
            if PRICE_FETCH_DEBUG:
                print(f"[price_debug] get_price_with_change using nimble price for {symbol.upper()}, AV needed for change%")

        # AV fallback: only reached if Nimble missed price or change_percent
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
                    if price_str and result["price"] is None:
                        result['price'] = Decimal(price_str)
                        self._set_cached_price(symbol, result['price'])
                    if change_str and result["change_percent"] is None:
                        result['change_percent'] = Decimal(change_str)
                        self._set_cached_change_percent(symbol, result["change_percent"])
            else:
                quote = raw.get('Global Quote', raw)
                price_str = (quote.get('05. price') or quote.get('price') or '').replace('%', '')
                change_str = (quote.get('10. change percent') or quote.get('change percent') or '').replace('%', '')
                if price_str and result["price"] is None:
                    result['price'] = Decimal(str(price_str))
                    self._set_cached_price(symbol, result['price'])
                if change_str and result["change_percent"] is None:
                    result['change_percent'] = Decimal(str(change_str))
                    self._set_cached_change_percent(symbol, result["change_percent"])
        except Exception as e:
            print(f"get_price_with_change failed for {symbol}: {e}")

        if PRICE_FETCH_DEBUG:
            source = "nimble+alphavantage" if nimble_data.get("price") is not None else "alphavantage"
            print(f"[price_debug] final source={source} for {symbol.upper()} result={result}")
        return result

    def get_prices_batch(self, symbols: list) -> Dict[str, Decimal]:
        """
        Get prices for multiple stocks.

        Fetches sequentially with a delay between calls to respect
        Alpha Vantage free tier limits (5 requests/minute).
        Cached symbols skip the delay.

        Args:
            symbols: List of stock ticker symbols

        Returns:
            Dict mapping symbol to price
        """
        prices = {}
        for i, symbol in enumerate(symbols):
            # Skip delay if price is already cached
            needs_api_call = self._get_cached_price(symbol) is None
            if needs_api_call and i > 0:
                time.sleep(self._BATCH_DELAY)

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
