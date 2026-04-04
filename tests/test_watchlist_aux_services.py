from watchlist.earnings_calendar_service import get_watchlist_earnings_calendar
from watchlist.news_recap_service import get_watchlist_news_recap


def test_earnings_calendar_returns_entries_for_symbols():
    items = get_watchlist_earnings_calendar(
        user_id="u1",
        watchlist_id="w1",
        symbols=["aapl", "AAPL", "msft"],
    )

    assert len(items) == 2
    assert items[0]["symbol"] == "AAPL"
    assert items[1]["symbol"] == "MSFT"
    assert all("report_date" in item for item in items)


def test_news_recap_returns_empty_when_provider_unavailable(monkeypatch):
    import types
    import sys

    monkeypatch.setitem(
        sys.modules,
        "news_service",
        types.SimpleNamespace(
            get_briefing=lambda: (_ for _ in ()).throw(
                RuntimeError("provider unavailable")
            )
        ),
    )
    items = get_watchlist_news_recap("u1", "w1", ["NVDA"])
    assert items == []
