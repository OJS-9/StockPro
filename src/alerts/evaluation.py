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

import requests

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


def _build_alert_email_html(
    symbol: str, price: float, target: float, direction: str
) -> str:
    """Render a StockPro-styled HTML email for a fired price alert.

    Email-safe: table layout, inline styles, explicit dark-theme colors
    (design tokens from the SPA). No external CSS or web fonts required.
    """
    up = (direction or "").lower() == "above"
    accent = "#22c55e" if up else "#ef4444"  # accent-up / accent-down
    arrow = "&#9650;" if up else "&#9660;"  # up / down triangle
    base_url = (os.getenv("APP_BASE_URL") or "https://stock-pro.org").rstrip("/")
    ticker_url = f"{base_url}/ticker/{symbol}"
    price_str = _format_money(price)
    target_str = _format_money(target)
    body_font = (
        "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
    )
    display_font = "'Nunito'," + body_font
    return f"""<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background-color:#0c0a09;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#0c0a09;padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px;width:100%;background-color:#1c1917;border:1px solid #292524;border-radius:16px;">
          <tr>
            <td style="padding:28px 32px 0 32px;">
              <div style="font-family:{display_font};font-size:18px;font-weight:800;color:#f5f5f4;letter-spacing:-0.3px;">StockPro</div>
              <div style="font-family:{body_font};font-size:12px;font-weight:600;color:#a8a29e;text-transform:uppercase;letter-spacing:1px;margin-top:6px;">Price Alert</div>
            </td>
          </tr>
          <tr>
            <td style="padding:20px 32px 0 32px;">
              <div style="font-family:{display_font};font-size:30px;font-weight:800;color:#f5f5f4;">{symbol}</div>
              <div style="font-family:{display_font};font-size:38px;font-weight:800;color:{accent};margin-top:4px;">{arrow}&nbsp;{price_str}</div>
            </td>
          </tr>
          <tr>
            <td style="padding:12px 32px 0 32px;">
              <p style="font-family:{body_font};font-size:15px;line-height:22px;color:#d6d3d1;margin:0;">{symbol} is now <strong style="color:#f5f5f4;">{price_str}</strong>, {direction} your target of <strong style="color:#f5f5f4;">{target_str}</strong>.</p>
            </td>
          </tr>
          <tr>
            <td style="padding:28px 32px 0 32px;">
              <table role="presentation" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="background-color:#f5f5f4;border-radius:9999px;">
                    <a href="{ticker_url}" style="display:inline-block;padding:12px 28px;font-family:{body_font};font-size:14px;font-weight:700;color:#0c0a09;text-decoration:none;border-radius:9999px;">View {symbol} on StockPro</a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:28px 32px;">
              <p style="font-family:{body_font};font-size:12px;line-height:18px;color:#78716c;margin:24px 0 0 0;border-top:1px solid #292524;padding-top:20px;">You're receiving this because you set a price alert on StockPro. This one-time alert has now been turned off.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _send_email_alert_if_configured(
    db,
    user_id: str,
    symbol: str,
    body: str,
    price: float,
    target: float,
    direction: str,
) -> None:
    """Best-effort email delivery via Brevo for users with an email on file.

    Sends a StockPro-styled HTML email with a plain-text fallback. Skips
    silently if Brevo is not configured or the user has no email. Never logs
    the email address (it is an AES-encrypted field).
    """
    api_key = (os.getenv("BREVO_API_KEY") or "").strip()
    from_email = (os.getenv("ALERT_FROM_SENDER") or "").strip()
    if not api_key or not from_email:
        return
    try:
        user = db.get_user_by_id(user_id)
        email = (user or {}).get("email") if user else None
        if not email:
            return
        resp = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": api_key, "accept": "application/json"},
            json={
                "sender": {"email": from_email, "name": "StockPro Alerts"},
                "to": [{"email": email}],
                "subject": f"{symbol} price alert",
                "htmlContent": _build_alert_email_html(
                    symbol, price, target, direction
                ),
                "textContent": body,
            },
            timeout=15,
        )
        if resp.status_code >= 400:
            logger.warning(
                "Brevo alert email failed for user_id=%s symbol=%s: status=%s",
                user_id,
                symbol,
                resp.status_code,
            )
    except Exception:
        logger.exception(
            "Email alert send failed for user_id=%s symbol=%s", user_id, symbol
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
        # Stock alerts only evaluate during US market hours (skip gate with env var)
        if at_alert == "stock" and not _us_market_open():
            if os.getenv("STOCKPRO_ALERT_SKIP_MARKET_HOURS", "").lower() not in ("1", "true", "yes"):
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
            _send_email_alert_if_configured(
                db, alert["user_id"], sym, body, price, target, direction
            )
            # One-shot: deactivate alert after successful trigger
            try:
                db.set_price_alert_active(alert["alert_id"], alert["user_id"], False)
            except Exception:
                logger.exception("failed to deactivate alert %s after trigger", alert.get("alert_id"))
            try:
                db.admin_log_event("alert_triggered", alert["user_id"], {
                    "symbol": sym, "alert_id": alert["alert_id"], "direction": direction,
                    "target": float(target), "price": float(price),
                })
            except Exception:
                pass
            fired += 1
        except Exception:
            logger.exception(
                "record_price_alert_trigger failed for alert_id=%s",
                alert.get("alert_id"),
            )
    return fired
