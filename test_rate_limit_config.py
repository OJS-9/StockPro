"""Sanity checks for Flask-Limiter env-driven strings (Phase 1.6)."""


def test_continue_conversation_rate_limit_env(monkeypatch):
    import app as app_module

    monkeypatch.delenv("STOCKPRO_RATE_LIMIT_CONTINUE", raising=False)
    assert app_module._continue_conversation_rate_limit() == "60 per hour"

    monkeypatch.setenv("STOCKPRO_RATE_LIMIT_CONTINUE", "10 per minute")
    assert app_module._continue_conversation_rate_limit() == "10 per minute"


def test_chat_report_rate_limit_env(monkeypatch):
    import app as app_module

    monkeypatch.delenv("STOCKPRO_RATE_LIMIT_CHAT_REPORT", raising=False)
    assert app_module._chat_report_rate_limit() == "40 per hour"

    monkeypatch.setenv("STOCKPRO_RATE_LIMIT_CHAT_REPORT", "5 per minute")
    assert app_module._chat_report_rate_limit() == "5 per minute"
