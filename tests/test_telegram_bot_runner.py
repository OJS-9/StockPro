from telegram_bot_runner import parse_research_args, summarize_report_text


def test_parse_research_args_defaults():
    ticker, trade_type = parse_research_args(["nvda"])
    assert ticker == "NVDA"
    assert trade_type == "Investment"


def test_parse_research_args_with_trade_type():
    ticker, trade_type = parse_research_args(["aapl", "Swing", "Trade"])
    assert ticker == "AAPL"
    assert trade_type == "Swing Trade"


def test_summarize_report_text_truncates():
    text = "x" * 40
    out = summarize_report_text(text, max_len=20)
    assert out.endswith("...")
    assert len(out) == 20


def test_run_bot_uses_update_all_types(monkeypatch):
    import types
    import telegram_bot_runner

    called = {}

    class DummyApp:
        def run_polling(self, allowed_updates=None):
            called["allowed_updates"] = allowed_updates

    monkeypatch.setattr(telegram_bot_runner, "build_telegram_app", lambda: DummyApp())
    monkeypatch.setitem(
        __import__("sys").modules,
        "telegram",
        types.SimpleNamespace(Update=types.SimpleNamespace(ALL_TYPES=["message"])),
    )

    telegram_bot_runner.run_bot()
    assert called["allowed_updates"] == ["message"]
