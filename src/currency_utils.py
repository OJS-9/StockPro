"""
Currency utilities for TASE (Tel Aviv Stock Exchange) support.
Handles ILA/ILS conversion and USD/ILS exchange rates.
"""

import logging
import time
from decimal import Decimal

logger = logging.getLogger(__name__)

_fx_cache: dict = {}
_FX_TTL_SECONDS = 900  # 15 minutes
_FALLBACK_USD_ILS = Decimal("3.6")


def is_tase_ticker(symbol: str) -> bool:
    return symbol.upper().endswith(".TA")


def detect_currency(symbol: str) -> str:
    return "ILS" if is_tase_ticker(symbol) else "USD"


def ila_to_ils(price: Decimal) -> Decimal:
    return price / 100


def get_usd_ils_rate() -> Decimal:
    cached = _fx_cache.get("USDILS")
    if cached and time.time() - cached["ts"] < _FX_TTL_SECONDS:
        return cached["rate"]

    try:
        import yfinance as yf

        rate = yf.Ticker("USDILS=X").fast_info.last_price
        if rate and rate > 0:
            result = Decimal(str(rate))
            _fx_cache["USDILS"] = {"rate": result, "ts": time.time()}
            return result
    except Exception:
        logger.warning("Failed to fetch USD/ILS rate, using fallback")

    return _FALLBACK_USD_ILS


def convert_to_usd(amount: Decimal, currency: str) -> Decimal:
    if currency == "USD":
        return amount
    if currency == "ILS":
        rate = get_usd_ils_rate()
        return amount / rate
    return amount
