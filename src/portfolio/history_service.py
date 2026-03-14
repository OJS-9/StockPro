"""
Portfolio value history service - computes monthly portfolio values.
"""

import os
import calendar
import requests
from decimal import Decimal
from datetime import datetime, date
from typing import List, Dict, Optional

from data_providers.crypto_provider import CryptoDataProvider

_ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"

# Module-level price cache: symbol -> {'prices': {date_str: float}, 'fetched_at': datetime}
_price_cache: Dict[str, dict] = {}
_CACHE_TTL_HOURS = 24


def _cache_valid(entry: dict) -> bool:
    delta = datetime.utcnow() - entry['fetched_at']
    return delta.total_seconds() < _CACHE_TTL_HOURS * 3600


def _month_end_dates(months: int) -> List[date]:
    """Return list of month-end dates ending with today, going back `months` months."""
    today = date.today()
    ends = []
    year, month = today.year, today.month
    for _ in range(months):
        last_day = calendar.monthrange(year, month)[1]
        ends.append(date(year, month, min(last_day, today.day if (year == today.year and month == today.month) else last_day)))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    ends.reverse()
    return ends


class PortfolioHistoryService:

    def __init__(self, db=None):
        self._db = db

    @property
    def db(self):
        if self._db is None:
            from database import get_database_manager
            self._db = get_database_manager()
        return self._db

    def get_monthly_values(self, portfolio_id: str, months: int = 12) -> List[dict]:
        """
        Compute monthly portfolio values for the past `months` months.

        Returns:
            List of {'date': 'Mar 2025', 'value': 12450.00}
        """
        transactions = self.db.get_all_portfolio_transactions(portfolio_id)

        if not transactions:
            month_ends = _month_end_dates(months)
            return [{'date': d.strftime('%b %Y'), 'value': 0.0} for d in month_ends]

        # Group transactions by symbol
        by_symbol: Dict[str, list] = {}
        asset_type_map: Dict[str, str] = {}
        for txn in transactions:
            sym = txn['symbol']
            by_symbol.setdefault(sym, []).append(txn)
            asset_type_map[sym] = txn['asset_type']

        month_ends = _month_end_dates(months)

        # Fetch price histories per symbol
        stock_prices: Dict[str, Dict[str, float]] = {}
        crypto_prices: Dict[str, Dict[str, float]] = {}

        for sym, asset_type in asset_type_map.items():
            if asset_type == 'stock':
                stock_prices[sym] = self._get_stock_prices(sym)
            else:
                crypto_prices[sym] = self._get_crypto_prices(sym)

        result = []
        for month_end in month_ends:
            total = 0.0
            for sym, txns in by_symbol.items():
                qty = self._qty_at_date(txns, month_end)
                if qty <= 0:
                    continue

                asset_type = asset_type_map[sym]
                if asset_type == 'stock':
                    prices = stock_prices.get(sym, {})
                else:
                    prices = crypto_prices.get(sym, {})

                price = self._lookup_price(prices, month_end, asset_type)
                if price is not None:
                    total += qty * price

            result.append({'date': month_end.strftime('%b %Y'), 'value': round(total, 2)})

        return result

    def _qty_at_date(self, transactions: list, as_of: date) -> float:
        """Replay transactions up to as_of date, return clamped quantity."""
        qty = Decimal('0')
        for txn in transactions:
            txn_date = txn['transaction_date']
            if isinstance(txn_date, datetime):
                txn_date = txn_date.date()
            if txn_date > as_of:
                break
            if txn['transaction_type'] == 'buy':
                qty += txn['quantity']
            else:
                qty -= txn['quantity']
        if qty < 0:
            qty = Decimal('0')
        return float(qty)

    def _get_stock_prices(self, symbol: str) -> Dict[str, float]:
        """Fetch monthly adjusted close prices from Alpha Vantage. Returns {YYYY-MM-DD: price}."""
        global _price_cache
        cache_key = f"stock:{symbol}"
        if cache_key in _price_cache and _cache_valid(_price_cache[cache_key]):
            return _price_cache[cache_key]['prices']

        api_key = os.getenv('ALPHA_VANTAGE_API_KEY', '')
        if not api_key:
            return {}

        try:
            resp = requests.get(
                _ALPHA_VANTAGE_URL,
                params={
                    'function': 'TIME_SERIES_MONTHLY_ADJUSTED',
                    'symbol': symbol,
                    'apikey': api_key,
                },
                timeout=15
            )
            if not resp.ok:
                return {}
            data = resp.json()
            series = data.get('Monthly Adjusted Time Series', {})
            prices = {k: float(v['5. adjusted close']) for k, v in series.items()}
            _price_cache[cache_key] = {'prices': prices, 'fetched_at': datetime.utcnow()}
            return prices
        except Exception:
            return {}

    def _get_crypto_prices(self, symbol: str) -> Dict[str, float]:
        """Fetch daily price history from CoinGecko. Returns {YYYY-MM-DD: price}."""
        global _price_cache
        cache_key = f"crypto:{symbol}"
        if cache_key in _price_cache and _cache_valid(_price_cache[cache_key]):
            return _price_cache[cache_key]['prices']

        crypto_provider = CryptoDataProvider()
        coin_id = crypto_provider._get_coin_id(symbol)
        if not coin_id:
            return {}

        try:
            resp = requests.get(
                f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
                params={'vs_currency': 'usd', 'days': 400},
                timeout=15
            )
            if not resp.ok:
                return {}
            data = resp.json()
            prices_raw = data.get('prices', [])
            prices: Dict[str, float] = {}
            for ts_ms, price in prices_raw:
                d = date.fromtimestamp(ts_ms / 1000)
                prices[d.strftime('%Y-%m-%d')] = price
            _price_cache[cache_key] = {'prices': prices, 'fetched_at': datetime.utcnow()}
            return prices
        except Exception:
            return {}

    def _lookup_price(self, prices: Dict[str, float], target: date, asset_type: str) -> Optional[float]:
        """Find closest available price to target date."""
        if not prices:
            return None

        target_str = target.strftime('%Y-%m-%d')
        if target_str in prices:
            return prices[target_str]

        # For stocks: Alpha Vantage returns YYYY-MM-DD as last day of the month series
        # Try searching backwards up to 31 days
        for days_back in range(1, 32):
            candidate = date.fromordinal(target.toordinal() - days_back)
            candidate_str = candidate.strftime('%Y-%m-%d')
            if candidate_str in prices:
                return prices[candidate_str]

        return None


_history_service: Optional[PortfolioHistoryService] = None


def get_history_service() -> PortfolioHistoryService:
    global _history_service
    if _history_service is None:
        _history_service = PortfolioHistoryService()
    return _history_service
