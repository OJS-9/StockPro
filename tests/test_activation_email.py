"""Unit tests for the 24h post-signup activation email (issue #120)."""

import importlib.util
import os
from unittest.mock import MagicMock

from email_service import send_activation_email


class _Resp:
    def __init__(self, status_code=201):
        self.status_code = status_code


def _capture_post(captured, status_code=201):
    def _fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["to"] = json["to"]
        captured["subject"] = json["subject"]
        captured["text"] = json["textContent"]
        captured["html"] = json["htmlContent"]
        return _Resp(status_code)

    return _fake_post


def test_activation_email_en_with_ticker(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setenv("ALERT_FROM_SENDER", "alerts@stockpro.test")
    monkeypatch.setenv("APP_BASE_URL", "https://stock-pro.org")
    captured = {}
    monkeypatch.setattr("requests.post", _capture_post(captured))

    ok = send_activation_email("user@example.com", "Sam", "AAPL", "en")

    assert ok is True
    assert captured["url"] == "https://api.brevo.com/v3/smtp/email"
    assert captured["to"] == [{"email": "user@example.com"}]
    assert "AAPL" in captured["subject"]
    assert "Sam" in captured["html"]
    # CTA points at the real add-to-portfolio route from issue #111.
    assert "https://stock-pro.org/portfolio?add=AAPL" in captured["html"]
    assert "https://stock-pro.org/portfolio?add=AAPL" in captured["text"]
    assert "StockPro" in captured["html"]


def test_activation_email_he_is_rtl(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setenv("ALERT_FROM_SENDER", "alerts@stockpro.test")
    captured = {}
    monkeypatch.setattr("requests.post", _capture_post(captured))

    ok = send_activation_email("user@example.com", "Dana", "TSLA", "he")

    assert ok is True
    assert 'dir="rtl"' in captured["html"]
    # Hebrew copy carries the ticker and a Hebrew word.
    assert "TSLA" in captured["subject"]
    assert "היי" in captured["html"]  # "היי" greeting


def test_activation_email_fallback_without_ticker(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setenv("ALERT_FROM_SENDER", "alerts@stockpro.test")
    monkeypatch.setenv("APP_BASE_URL", "https://stock-pro.org")
    captured = {}
    monkeypatch.setattr("requests.post", _capture_post(captured))

    ok = send_activation_email("user@example.com", "Sam", None, "en")

    assert ok is True
    # Fallback subject does not embed a ticker; CTA links to bare /portfolio.
    assert "set up on StockPro" in captured["subject"]
    assert "https://stock-pro.org/portfolio" in captured["html"]
    assert "add=" not in captured["html"]


def test_activation_email_unconfigured_is_noop(monkeypatch):
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    monkeypatch.delenv("ALERT_FROM_SENDER", raising=False)

    def _boom(*args, **kwargs):
        raise AssertionError("requests.post must not be called when unconfigured")

    monkeypatch.setattr("requests.post", _boom)
    assert send_activation_email("user@example.com", "Sam", "AAPL", "en") is False


def test_activation_email_missing_email_is_noop(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setenv("ALERT_FROM_SENDER", "alerts@stockpro.test")

    def _boom(*args, **kwargs):
        raise AssertionError("requests.post must not be called without an email")

    monkeypatch.setattr("requests.post", _boom)
    assert send_activation_email("", "Sam", "AAPL", "en") is False


def test_activation_email_provider_error_returns_false(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setenv("ALERT_FROM_SENDER", "alerts@stockpro.test")
    captured = {}
    monkeypatch.setattr("requests.post", _capture_post(captured, status_code=500))
    assert send_activation_email("user@example.com", "Sam", "AAPL", "en") is False


def test_activation_email_swallows_exception(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setenv("ALERT_FROM_SENDER", "alerts@stockpro.test")

    def _boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr("requests.post", _boom)
    # Must not raise, returns False.
    assert send_activation_email("user@example.com", "Sam", "AAPL", "en") is False


def _load_script():
    path = os.path.join(
        os.path.dirname(__file__), "..", "scripts", "send_activation_emails.py"
    )
    spec = importlib.util.spec_from_file_location("send_activation_emails", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_script_resets_flag_only_on_send_failure(monkeypatch):
    """The cron script sends each claimed user and resets the flag on failure."""
    monkeypatch.setenv("DATABASE_URL", "postgres://test")
    mod = _load_script()

    db = MagicMock()
    db.claim_activation_email_candidates.return_value = [
        {"user_id": "u1", "username": "Sam", "email": "a@x.test", "ticker": "AAPL", "language": "en"},
        {"user_id": "u2", "username": "Dana", "email": "b@x.test", "ticker": "TSLA", "language": "he"},
    ]
    monkeypatch.setattr("database.get_database_manager", lambda: db)

    # u1 succeeds, u2 fails.
    def _fake_send(email, username, ticker, language):
        return email == "a@x.test"

    monkeypatch.setattr("email_service.send_activation_email", _fake_send)

    rc = mod.main()
    assert rc == 0
    # Only the failed user's flag is reset for retry.
    db.reset_activation_email_flag.assert_called_once_with("u2")
