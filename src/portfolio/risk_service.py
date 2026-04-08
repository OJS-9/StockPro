"""
Portfolio risk metrics service.

Computes: Volatility, Sharpe Ratio, Max Drawdown, Beta vs S&P 500, Concentration Risk.
Uses yfinance for historical daily returns.
"""

import logging
import math
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_RISK_FREE_RATE = 0.05  # 5% annualised (approximate US T-bill)
_TRADING_DAYS = 252


def _fetch_daily_returns(symbol: str, period: str = "1y") -> List[float]:
    """Return list of daily percentage returns for a symbol."""
    try:
        import yfinance as yf

        hist = yf.Ticker(symbol).history(period=period)
        if hist.empty or len(hist) < 2:
            return []
        closes = list(hist["Close"])
        return [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]
    except Exception as e:
        logger.debug("yfinance returns error for %s: %s", symbol, e)
        return []


def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stdev(values: List[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    variance = sum((v - m) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def _covariance(x: List[float], y: List[float]) -> float:
    n = min(len(x), len(y))
    if n < 2:
        return 0.0
    mx, my = _mean(x[:n]), _mean(y[:n])
    return sum((x[i] - mx) * (y[i] - my) for i in range(n)) / (n - 1)


def compute_risk_metrics(portfolio_id: str, holdings: List[Dict]) -> Dict:
    """
    Compute risk metrics for a portfolio.

    Args:
        portfolio_id: Portfolio ID (unused but kept for interface symmetry)
        holdings: List of holding dicts with 'symbol', 'market_value', 'asset_type'

    Returns:
        Dict with volatility, sharpe_ratio, max_drawdown, beta, concentration_risk
    """
    stock_holdings = [
        h for h in holdings
        if h.get("asset_type") == "stock" and float(h.get("market_value") or 0) > 0
    ]

    if not stock_holdings:
        return {}

    total_value = sum(float(h.get("market_value") or 0) for h in holdings)
    if total_value <= 0:
        return {}

    # Weights by market value (stocks only for returns; treat crypto as having 0 return for now)
    weights = {
        h["symbol"]: float(h.get("market_value") or 0) / total_value
        for h in stock_holdings
    }

    # Fetch daily returns per symbol
    symbol_returns: Dict[str, List[float]] = {}
    for sym in weights:
        symbol_returns[sym] = _fetch_daily_returns(sym)

    if not any(symbol_returns.values()):
        return {}

    # Align lengths to shortest series
    min_len = min((len(r) for r in symbol_returns.values() if r), default=0)
    if min_len < 20:  # not enough data
        return {}

    # Weighted portfolio daily returns
    portfolio_returns = []
    for i in range(min_len):
        day_return = sum(
            weights[sym] * symbol_returns[sym][i]
            for sym in weights
            if symbol_returns.get(sym)
        )
        portfolio_returns.append(day_return)

    # Annualised volatility
    daily_vol = _stdev(portfolio_returns)
    volatility = daily_vol * math.sqrt(_TRADING_DAYS)

    # Annualised return
    mean_daily = _mean(portfolio_returns)
    annualised_return = mean_daily * _TRADING_DAYS

    # Sharpe ratio
    sharpe = (annualised_return - _RISK_FREE_RATE) / volatility if volatility > 0 else None

    # Max drawdown
    peak = portfolio_returns[0] if portfolio_returns else 0
    cumulative = 1.0
    running_peak = 1.0
    max_drawdown = 0.0
    for r in portfolio_returns:
        cumulative *= (1 + r)
        if cumulative > running_peak:
            running_peak = cumulative
        drawdown = (running_peak - cumulative) / running_peak if running_peak > 0 else 0
        if drawdown > max_drawdown:
            max_drawdown = drawdown

    # Beta vs SPY
    beta = None
    try:
        spy_returns = _fetch_daily_returns("SPY")
        if spy_returns and len(spy_returns) >= min_len:
            spy_aligned = spy_returns[:min_len]
            port_aligned = portfolio_returns[:min_len]
            spy_var = _stdev(spy_aligned) ** 2
            if spy_var > 0:
                beta = _covariance(port_aligned, spy_aligned) / spy_var
    except Exception as e:
        logger.debug("Beta computation failed: %s", e)

    # Concentration risk: largest single holding % of total portfolio
    concentration = max(
        float(h.get("market_value") or 0) / total_value * 100
        for h in holdings
    ) if holdings else None

    return {
        "volatility": round(volatility * 100, 2) if volatility else None,  # as %
        "sharpe_ratio": round(sharpe, 3) if sharpe is not None else None,
        "max_drawdown": round(max_drawdown * 100, 2),  # as %
        "beta": round(beta, 3) if beta is not None else None,
        "concentration_risk": round(concentration, 1) if concentration is not None else None,
    }
