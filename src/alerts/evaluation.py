"""
Evaluate active price alerts against price_cache after quotes update.
"""

import logging
import os
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Iterable, List
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def _to_float(x: Any) -> float:
    if x is None:
        raise TypeError("price is None")
    if isinstance(x, Decimal):
        return float(x)
    return float(x)


def condition_met(direction: str, price: float, target: float) -> bool:
    d = (direction or "").lower()
    if d == "above":
        return price >= target
    if d == "below":
        return price <= target
    return False


def _format_money(x: float) -> str:
    if abs(x) >= 1000:
        return f"${x:,.2f}"
    return f"${x:.4g}"


def _cooldown() -> timedelta:
    sec = float(os.getenv("STOCKPRO_ALERT_COOLDOWN_SEC", "3600"))
    return timedelta(seconds=sec)


_ET = ZoneInfo("America/New_York")


def _us_market_open() -> bool:
    """Return True if US stock market is currently open (Mon-Fri 9:30-16:00 ET)."""
    now_et = datetime.now(_ET)
    if now_et.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    t = now_et.time()
    from datetime import time as _time
    return _time(9, 30) <= t <= _time(16, 0)


def _send_telegram_alert_if_connected(db, user_id: str, symbol: str, body: str) -> None:
    """Best-effort Telegram delivery for users who linked a chat id."""
    try:
        user = db.get_user_by_id(user_id)
        chat_id = (user or {}).get("telegram_chat_id") if user else None
        if not chat_id:
            return
        from telegram_service import send_telegram_text_sync

        send_telegram_text_sync(str(chat_id), f"{symbol} alert\n{body}")
    except Exception:
        logger.exception(
            "Telegram send failed for user_id=%s symbol=%s", user_id, symbol
        )


def evaluate_alerts_for_symbols(db, symbols: Iterable[str]) -> int:
    """
    Check active alerts for the given symbols against price_cache.
    Inserts notification rows and updates last_triggered_at when conditions match
    and cooldown since last_triggered_at has elapsed.
    """
    syms = list({str(s).upper() for s in symbols if s})
    if not syms:
        return 0
    alerts: List = db.list_active_alerts_for_symbols(syms)
    if not alerts:
        return 0
    cache = db.get_cached_prices(syms)
    cooldown = _cooldown()
    now = datetime.utcnow()
    fired = 0
    for alert in alerts:
        sym = alert["symbol"]
        row = cache.get(sym)
        if not row:
            continue
        at_cache = (row.get("asset_type") or "stock").lower()
        at_alert = (alert.get("asset_type") or "stock").lower()
        if at_cache != at_alert:
            continue
        # Stock alerts only evaluate during US market hours
        if at_alert == "stock" and not _us_market_open():
            continue
        try:
            price = _to_float(row.get("price"))
        except (TypeError, ValueError):
            continue
        try:
            target = _to_float(alert.get("target_price"))
        except (TypeError, ValueError):
            continue
        direction = (alert.get("direction") or "").lower()
        if not condition_met(direction, price, target):
            continue
        last = alert.get("last_triggered_at")
        if last is not None:
            if getattr(last, "tzinfo", None):
                last = last.replace(tzinfo=None)
            if now - last < cooldown:
                continue
        body = (
            f"{sym} is now {_format_money(price)} "
            f"({direction} your target of {_format_money(target)})."
        )
        nid = str(uuid.uuid4())
        try:
            db.record_price_alert_trigger(
                nid, alert["user_id"], alert["alert_id"], sym, body
            )
            _send_telegram_alert_if_connected(db, alert["user_id"], sym, body)
            fired += 1
        except Exception:
            logger.exception(
                "record_price_alert_trigger failed for alert_id=%s",
                alert.get("alert_id"),
            )
    return fired
