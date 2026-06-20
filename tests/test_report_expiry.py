"""Unit tests for the 7-day report expiry nudge email (issue #130)."""

from email_service import send_report_expiry_email


class _Resp:
    def __init__(self, status_code=201):
        self.status_code = status_code


def _capture_post(captured, status_code=201):
    def _fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["to"] = json["to"]
        captured["sender"] = json["sender"]
        captured["subject"] = json["subject"]
        captured["text"] = json["textContent"]
        captured["html"] = json["htmlContent"]
        return _Resp(status_code)

    return _fake_post


def test_expiry_en(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setenv("ALERT_FROM_SENDER", "alerts@stockpro.test")
    monkeypatch.setenv("APP_BASE_URL", "https://stock-pro.org")
    captured = {}
    monkeypatch.setattr("requests.post", _capture_post(captured))

    ok = send_report_expiry_email("user@example.com", "Sam", "NVDA", "en")

    assert ok is True
    assert captured["to"] == [{"email": "user@example.com"}]
    # Sends under the "StockPro Alerts" sender name (matches the price-alert email).
    assert captured["sender"]["name"] == "StockPro Alerts"
    assert "NVDA" in captured["subject"]
    assert "7 days old" in captured["subject"]
    assert "Sam" in captured["html"]
    # CTA links to the research wizard with the ticker prefilled.
    assert "https://stock-pro.org/research?ticker=NVDA" in captured["html"]
    assert "https://stock-pro.org/research?ticker=NVDA" in captured["text"]


def test_expiry_he_is_rtl(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setenv("ALERT_FROM_SENDER", "alerts@stockpro.test")
    captured = {}
    monkeypatch.setattr("requests.post", _capture_post(captured))

    ok = send_report_expiry_email("user@example.com", "Dana", "AAPL", "he")

    assert ok is True
    assert 'dir="rtl"' in captured["html"]
    assert "היי" in captured["html"]  # Hebrew greeting
    assert "AAPL" in captured["subject"]


def test_expiry_unconfigured_is_noop(monkeypatch):
    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    monkeypatch.delenv("ALERT_FROM_SENDER", raising=False)

    def _boom(*args, **kwargs):
        raise AssertionError("requests.post must not be called when unconfigured")

    monkeypatch.setattr("requests.post", _boom)
    assert send_report_expiry_email("user@example.com", "Sam", "NVDA", "en") is False


def test_expiry_missing_email_or_ticker_is_noop(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setenv("ALERT_FROM_SENDER", "alerts@stockpro.test")

    def _boom(*args, **kwargs):
        raise AssertionError("requests.post must not be called")

    monkeypatch.setattr("requests.post", _boom)
    assert send_report_expiry_email("", "Sam", "NVDA", "en") is False
    assert send_report_expiry_email("user@example.com", "Sam", "", "en") is False


def test_expiry_provider_error_returns_false(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setenv("ALERT_FROM_SENDER", "alerts@stockpro.test")
    captured = {}
    monkeypatch.setattr("requests.post", _capture_post(captured, status_code=500))
    assert send_report_expiry_email("user@example.com", "Sam", "NVDA", "en") is False
