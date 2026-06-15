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


def _post_brevo_email(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: str,
    sender_name: str = "StockPro",
) -> bool:
    """POST a single email to Brevo. Returns True on a 2xx/3xx response.

    Silently returns False (logging a warning) if Brevo is not configured or the
    request fails. Never logs the recipient address (email is an encrypted field).
    """
    api_key = (os.getenv("BREVO_API_KEY") or "").strip()
    from_email = (os.getenv("ALERT_FROM_SENDER") or "").strip()
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
