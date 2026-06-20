"""
Transactional email sending via Brevo.

Currently powers the 24h post-signup activation nudge (issue #120). Reuses the
same Brevo credentials as the price-alert email (BREVO_API_KEY,
ALERT_FROM_SENDER). All sends are best-effort: if Brevo is not configured or the
provider returns an error, the functions log and return False instead of raising,
so callers never crash on a delivery failure.
"""

import logging
import os
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_BODY_FONT = (
    "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
)
_DISPLAY_FONT = "'Nunito'," + _BODY_FONT


def _base_url() -> str:
    return (os.getenv("APP_BASE_URL") or "https://stock-pro.org").rstrip("/")


def _alerts_from_sender() -> str:
    """From-address for alert-style emails (the report expiry nudge).

    Env-overridable; defaults to alerts@stock-pro.org so the nudge sends from the
    alerts mailbox rather than the personal ALERT_FROM_SENDER (or@stock-pro.org)
    used by the activation email. Must be a verified sender in Brevo.
    """
    return (os.getenv("ALERTS_FROM_SENDER") or "alerts@stock-pro.org").strip()


def _post_brevo_email(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: str,
    sender_name: str = "StockPro",
    from_email: Optional[str] = None,
) -> bool:
    """POST a single email to Brevo. Returns True on a 2xx/3xx response.

    `from_email` overrides the default sender address (ALERT_FROM_SENDER env).
    Silently returns False (logging a warning) if Brevo is not configured or the
    request fails. Never logs the recipient address (email is an encrypted field).
    """
    api_key = (os.getenv("BREVO_API_KEY") or "").strip()
    from_email = (from_email or os.getenv("ALERT_FROM_SENDER") or "").strip()
    if not api_key or not from_email or not to_email:
        return False
    try:
        resp = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={"api-key": api_key, "accept": "application/json"},
            json={
                "sender": {"email": from_email, "name": sender_name},
                "to": [{"email": to_email}],
                "subject": subject,
                "htmlContent": html_content,
                "textContent": text_content,
            },
            timeout=15,
        )
        if resp.status_code >= 400:
            logger.warning("Brevo email failed: status=%s", resp.status_code)
            return False
        return True
    except Exception:
        logger.exception("Brevo email send raised")
        return False


def _activation_copy(username: str, ticker: Optional[str], language: str) -> dict:
    """Return subject + body strings for the activation email in en or he."""
    he = (language or "").strip().lower() == "he"
    base = _base_url()
    if ticker:
        cta_url = f"{base}/portfolio?add={ticker}"
    else:
        cta_url = f"{base}/portfolio"

    if he:
        if ticker:
            subject = f"הדוח שלך על {ticker} שמור - רוצה לעקוב אחריו?"
            intro = f"הרצת אתמול דוח על {ticker}. הניתוח שמור בחשבון שלך."
            step = (
                f"הצעד הבא הוא להוסיף את {ticker} לתיק כדי לעקוב אחרי הרווח וההפסד "
                f"ולקבל התראות מחיר כשהמניה זזה."
            )
            cta = f"הוספת {ticker} לתיק"
        else:
            subject = "החשבון שלך ב-StockPro מוכן - הנה הצעד הבא"
            intro = "החשבון שלך ב-StockPro מוכן לשימוש."
            step = (
                "הצעד הבא הוא ליצור תיק כדי לעקוב אחרי המניות שלך "
                "ולקבל התראות מחיר."
            )
            cta = "מעבר לתיק שלי"
        greeting = f"היי {username},"
        footer = "הצעד הזה לוקח 30 שניות."
        signoff = "צוות StockPro"
    else:
        if ticker:
            subject = f"Your {ticker} report is saved - ready to track it?"
            intro = (
                f"You ran a report on {ticker} yesterday. The analysis is saved "
                f"in your account."
            )
            step = (
                f"The next step is to add {ticker} to a portfolio so you can track "
                f"your P&L and get price alerts when it moves."
            )
            cta = f"Add {ticker} to a portfolio"
        else:
            subject = "You're set up on StockPro - here's what to do next"
            intro = "Your StockPro account is ready to go."
            step = (
                "The next step is to create a portfolio so you can track your "
                "holdings and get price alerts."
            )
            cta = "Go to my portfolio"
        greeting = f"Hi {username},"
        footer = "It takes 30 seconds."
        signoff = "The StockPro team"

    text_content = (
        f"{greeting}\n\n{intro}\n\n{step}\n\n{cta}: {cta_url}\n\n{footer}\n\n- {signoff}"
    )
    return {
        "subject": subject,
        "greeting": greeting,
        "intro": intro,
        "step": step,
        "cta": cta,
        "cta_url": cta_url,
        "footer": footer,
        "signoff": signoff,
        "text": text_content,
        "rtl": he,
    }


def _build_activation_email_html(copy: dict) -> str:
    """Render a StockPro-styled dark-theme HTML email from a copy dict.

    Email-safe: table layout, inline styles, explicit colors (SPA design tokens),
    no external CSS or web fonts. Mirrors the price-alert email styling.
    """
    dir_attr = "rtl" if copy["rtl"] else "ltr"
    align = "right" if copy["rtl"] else "left"
    return f"""<!DOCTYPE html>
<html dir="{dir_attr}">
<body style="margin:0;padding:0;background-color:#0c0a09;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#0c0a09;padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="480" cellpadding="0" cellspacing="0" dir="{dir_attr}" style="max-width:480px;width:100%;background-color:#1c1917;border:1px solid #292524;border-radius:16px;">
          <tr>
            <td style="padding:28px 32px 0 32px;text-align:{align};">
              <div style="font-family:{_DISPLAY_FONT};font-size:18px;font-weight:800;color:#f5f5f4;letter-spacing:-0.3px;">StockPro</div>
            </td>
          </tr>
          <tr>
            <td style="padding:20px 32px 0 32px;text-align:{align};">
              <p style="font-family:{_BODY_FONT};font-size:16px;line-height:24px;color:#f5f5f4;margin:0;font-weight:700;">{copy['greeting']}</p>
            </td>
          </tr>
          <tr>
            <td style="padding:12px 32px 0 32px;text-align:{align};">
              <p style="font-family:{_BODY_FONT};font-size:15px;line-height:22px;color:#d6d3d1;margin:0;">{copy['intro']}</p>
              <p style="font-family:{_BODY_FONT};font-size:15px;line-height:22px;color:#d6d3d1;margin:16px 0 0 0;">{copy['step']}</p>
            </td>
          </tr>
          <tr>
            <td style="padding:28px 32px 0 32px;text-align:{align};">
              <table role="presentation" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="background-color:#f5f5f4;border-radius:9999px;">
                    <a href="{copy['cta_url']}" style="display:inline-block;padding:12px 28px;font-family:{_BODY_FONT};font-size:14px;font-weight:700;color:#0c0a09;text-decoration:none;border-radius:9999px;">{copy['cta']}</a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:20px 32px 0 32px;text-align:{align};">
              <p style="font-family:{_BODY_FONT};font-size:14px;line-height:20px;color:#a8a29e;margin:0;">{copy['footer']}</p>
            </td>
          </tr>
          <tr>
            <td style="padding:24px 32px 28px 32px;text-align:{align};">
              <p style="font-family:{_BODY_FONT};font-size:13px;line-height:18px;color:#78716c;margin:24px 0 0 0;border-top:1px solid #292524;padding-top:20px;">- {copy['signoff']}</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def send_activation_email(
    email: str,
    username: str,
    ticker: Optional[str],
    language: str = "en",
) -> bool:
    """Send the 24h post-signup activation nudge. Returns True if accepted by Brevo.

    Best-effort: returns False (no raise) if Brevo is unconfigured, the email is
    missing, or the provider errors, so the caller can retry on the next run.
    """
    if not email:
        return False
    copy = _activation_copy(username or "there", ticker, language)
    html = _build_activation_email_html(copy)
    return _post_brevo_email(email, copy["subject"], html, copy["text"])


def _report_expiry_copy(username: str, ticker: str, language: str) -> dict:
    """Return subject + body strings for the 7-day report expiry nudge (en/he).

    Same copy-dict shape as _activation_copy so it can render through
    _build_activation_email_html. The CTA points at the research wizard with the
    ticker prefilled (/research?ticker=...) so one click regenerates the report.
    """
    he = (language or "").strip().lower() == "he"
    cta_url = f"{_base_url()}/research?ticker={ticker}"

    if he:
        subject = f"הדוח שלך על {ticker} בן 7 ימים - השוק זז מאז"
        greeting = f"היי {username},"
        intro = (
            f"הדוח שלך ב-StockPro על {ticker} בן 7 ימים. שבוע הוא הרבה זמן בשוק - "
            f"מחירים, חדשות וסנטימנט יכלו להשתנות מאז."
        )
        step = "הרצת דוח חדש לוקחת דקה ונותנת לך ניתוח מעודכן לפעול לפיו."
        cta = f"הרצת דוח חדש על {ticker}"
        footer = "השוק זז מהר. תישאר מעודכן."
        signoff = "צוות StockPro"
    else:
        subject = f"Your {ticker} report is 7 days old - markets have moved"
        greeting = f"Hi {username},"
        intro = (
            f"Your StockPro report on {ticker} is now 7 days old. A week is a long "
            f"time in the market - prices, news, and sentiment may have shifted "
            f"since then."
        )
        step = (
            "Running a fresh report takes about a minute and gives you up-to-date "
            "analysis to act on."
        )
        cta = f"Generate a fresh {ticker} report"
        footer = "Markets move fast. Stay current."
        signoff = "The StockPro team"

    text_content = (
        f"{greeting}\n\n{intro}\n\n{step}\n\n{cta}: {cta_url}\n\n{footer}\n\n- {signoff}"
    )
    return {
        "subject": subject,
        "greeting": greeting,
        "intro": intro,
        "step": step,
        "cta": cta,
        "cta_url": cta_url,
        "footer": footer,
        "signoff": signoff,
        "text": text_content,
        "rtl": he,
    }


def send_report_expiry_email(
    email: str,
    username: str,
    ticker: str,
    language: str = "en",
) -> bool:
    """Send the 7-day report expiry nudge. Returns True if accepted by Brevo.

    Best-effort: returns False (no raise) if Brevo is unconfigured, the email or
    ticker is missing, or the provider errors, so the caller can retry next run.
    """
    if not email or not ticker:
        return False
    copy = _report_expiry_copy(username or "there", ticker, language)
    html = _build_activation_email_html(copy)
    # Send as "StockPro Alerts" <alerts@stock-pro.org> so the nudge reads as an
    # alert, distinct from the activation email's default "StockPro"
    # <or@stock-pro.org> sender.
    return _post_brevo_email(
        email,
        copy["subject"],
        html,
        copy["text"],
        sender_name="StockPro Alerts",
        from_email=_alerts_from_sender(),
    )


_ACCENT_UP = "#22c55e"
_ACCENT_DOWN = "#ef4444"


def _fmt_money(amount) -> str:
    try:
        return f"${amount:,.2f}"
    except Exception:
        return f"${amount}"


def _fmt_pct(pct) -> str:
    """Signed percent to one decimal, e.g. '+2.3%' / '-1.2%'."""
    return f"{pct:+.1f}%"


def _weekly_digest_copy(username: str, language: str, data: dict) -> dict:
    """Return subject + body fields for the weekly portfolio digest in en or he."""
    he = (language or "").strip().lower() == "he"
    cta_url = f"{_base_url()}/portfolio"

    total_value = data.get("total_value")
    week_change_pct = data.get("week_change_pct")
    top_mover = data.get("top_mover") or None

    value_str = _fmt_money(total_value)
    change_str = _fmt_pct(week_change_pct) if week_change_pct is not None else None
    change_up = week_change_pct is not None and week_change_pct >= 0

    mover_symbol = top_mover.get("symbol") if top_mover else None
    mover_pct = top_mover.get("pct") if top_mover else None
    mover_str = (
        f"{mover_symbol} {_fmt_pct(mover_pct)}"
        if mover_symbol is not None and mover_pct is not None
        else None
    )
    mover_up = mover_pct is not None and mover_pct >= 0

    if he:
        if change_str is not None:
            direction = "עלה ב-" if change_up else "ירד ב-"
            subject = f"התיק שלך {direction}{abs(week_change_pct):.1f}% השבוע"
        else:
            subject = "הסיכום השבועי של התיק שלך"
        greeting = f"היי {username},"
        value_label = "שווי התיק"
        change_label = "השבוע"
        mover_label = "המניה הבולטת"
        cta = "צפייה בתיק המלא"
        footer = "אפשר לבטל את הסיכום השבועי בכל עת בהגדרות."
        signoff = "צוות StockPro"
    else:
        if change_str is not None:
            direction = "up" if change_up else "down"
            subject = f"Your portfolio is {direction} {abs(week_change_pct):.1f}% this week"
        else:
            subject = "Your weekly portfolio update"
        greeting = f"Hi {username},"
        value_label = "Portfolio value"
        change_label = "This week"
        mover_label = "Top mover"
        cta = "View full portfolio"
        footer = "You can turn off weekly summaries anytime in Settings."
        signoff = "The StockPro team"

    text_lines = [greeting, "", f"{value_label}: {value_str}"]
    if change_str is not None:
        text_lines.append(f"{change_label}: {change_str}")
    if mover_str is not None:
        text_lines.append(f"{mover_label}: {mover_str}")
    text_lines += ["", f"{cta}: {cta_url}", "", footer, "", f"- {signoff}"]

    return {
        "subject": subject,
        "greeting": greeting,
        "value_label": value_label,
        "value_str": value_str,
        "change_label": change_label,
        "change_str": change_str,
        "change_up": change_up,
        "mover_label": mover_label,
        "mover_str": mover_str,
        "mover_up": mover_up,
        "cta": cta,
        "cta_url": cta_url,
        "footer": footer,
        "signoff": signoff,
        "text": "\n".join(text_lines),
        "rtl": he,
    }


def _build_weekly_digest_email_html(copy: dict) -> str:
    """Render a StockPro-styled dark-theme HTML digest from a copy dict.

    Email-safe: table layout, inline styles, explicit colors (SPA design tokens),
    no external CSS or web fonts. Mirrors the activation email styling.
    """
    dir_attr = "rtl" if copy["rtl"] else "ltr"
    align = "right" if copy["rtl"] else "left"

    stat_rows = (
        f'<p style="font-family:{_BODY_FONT};font-size:13px;line-height:18px;'
        f'color:#a8a29e;margin:0;">{copy["value_label"]}</p>'
        f'<p style="font-family:{_DISPLAY_FONT};font-size:30px;line-height:36px;'
        f'font-weight:800;color:#f5f5f4;margin:4px 0 0 0;">{copy["value_str"]}</p>'
    )
    if copy["change_str"] is not None:
        change_color = _ACCENT_UP if copy["change_up"] else _ACCENT_DOWN
        stat_rows += (
            f'<p style="font-family:{_BODY_FONT};font-size:15px;line-height:22px;'
            f'color:#d6d3d1;margin:16px 0 0 0;">{copy["change_label"]}: '
            f'<span style="color:{change_color};font-weight:700;">{copy["change_str"]}</span></p>'
        )
    if copy["mover_str"] is not None:
        mover_color = _ACCENT_UP if copy["mover_up"] else _ACCENT_DOWN
        stat_rows += (
            f'<p style="font-family:{_BODY_FONT};font-size:15px;line-height:22px;'
            f'color:#d6d3d1;margin:6px 0 0 0;">{copy["mover_label"]}: '
            f'<span style="color:{mover_color};font-weight:700;">{copy["mover_str"]}</span></p>'
        )

    return f"""<!DOCTYPE html>
<html dir="{dir_attr}">
<body style="margin:0;padding:0;background-color:#0c0a09;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#0c0a09;padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="480" cellpadding="0" cellspacing="0" dir="{dir_attr}" style="max-width:480px;width:100%;background-color:#1c1917;border:1px solid #292524;border-radius:16px;">
          <tr>
            <td style="padding:28px 32px 0 32px;text-align:{align};">
              <div style="font-family:{_DISPLAY_FONT};font-size:18px;font-weight:800;color:#f5f5f4;letter-spacing:-0.3px;">StockPro</div>
            </td>
          </tr>
          <tr>
            <td style="padding:20px 32px 0 32px;text-align:{align};">
              <p style="font-family:{_BODY_FONT};font-size:16px;line-height:24px;color:#f5f5f4;margin:0;font-weight:700;">{copy['greeting']}</p>
            </td>
          </tr>
          <tr>
            <td style="padding:16px 32px 0 32px;text-align:{align};">
              {stat_rows}
            </td>
          </tr>
          <tr>
            <td style="padding:28px 32px 0 32px;text-align:{align};">
              <table role="presentation" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="background-color:#f5f5f4;border-radius:9999px;">
                    <a href="{copy['cta_url']}" style="display:inline-block;padding:12px 28px;font-family:{_BODY_FONT};font-size:14px;font-weight:700;color:#0c0a09;text-decoration:none;border-radius:9999px;">{copy['cta']}</a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:24px 32px 28px 32px;text-align:{align};">
              <p style="font-family:{_BODY_FONT};font-size:13px;line-height:18px;color:#78716c;margin:24px 0 0 0;border-top:1px solid #292524;padding-top:20px;">{copy['footer']}</p>
              <p style="font-family:{_BODY_FONT};font-size:13px;line-height:18px;color:#78716c;margin:8px 0 0 0;">- {copy['signoff']}</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def send_weekly_digest_email(
    email: str,
    username: str,
    data: dict,
    language: str = "en",
) -> bool:
    """Send the weekly portfolio digest. Returns True if accepted by Brevo.

    `data` is the dict returned by PortfolioService.get_weekly_performance:
    total_value, week_change_pct (or None), top_mover (or None), holdings_count.

    Best-effort: returns False (no raise) if Brevo is unconfigured, the email or
    data is missing, or the provider errors, so the caller can retry next run.
    """
    if not email or not data:
        return False
    copy = _weekly_digest_copy(username or "there", language, data)
    html = _build_weekly_digest_email_html(copy)
    return _post_brevo_email(email, copy["subject"], html, copy["text"])
