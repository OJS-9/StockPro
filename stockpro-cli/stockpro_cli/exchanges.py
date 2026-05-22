"""Exchange and currency helpers for CLI symbol input and formatted output."""

EXCHANGES = ("US", "TASE")

_SUFFIX = {
    "US": "",
    "TASE": ".TA",
}

_CURRENCY_SYMBOLS = {
    "USD": "$",
    "ILS": "₪",
}


def apply_exchange_suffix(symbol: str, exchange: str) -> str:
    """Append the exchange suffix to a bare symbol if missing."""
    sym = symbol.strip().upper()
    suffix = _SUFFIX.get(exchange.upper(), "")
    if not suffix or sym.endswith(suffix):
        return sym
    return f"{sym}{suffix}"


def currency_symbol(currency: str | None) -> str:
    """Return the printable symbol for an ISO currency code."""
    if not currency:
        return "$"
    return _CURRENCY_SYMBOLS.get(currency.upper(), currency.upper() + " ")


def format_money(amount: float | int | None, currency: str | None = "USD") -> str:
    """Format an amount with the right currency symbol, e.g. $1,234.56 or ₪38.50."""
    if amount is None:
        return "-"
    return f"{currency_symbol(currency)}{float(amount):,.2f}"
