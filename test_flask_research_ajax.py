"""Research AJAX: /popup_start and /start_generation (agent / thread mocked)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent / "src"))


@pytest.fixture
def api_app():
    from app import app as flask_app

    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    flask_app.config["SECRET_KEY"] = "test-research-ajax"
    return flask_app


@pytest.fixture
def api_client(api_app):
    return api_app.test_client()


def test_popup_start_400_without_ticker_or_trade_type(api_client):
    with api_client.session_transaction() as sess:
        sess["user_id"] = "u1"
        sess["username"] = "u"
    resp = api_client.post("/popup_start", data={"ticker": "", "trade_type": ""})
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_popup_start_returns_questions_json(api_client):
    import app as app_module

    mock_agent = MagicMock()
    mock_agent.pending_questions = [
        {"question": "Goal?", "options": ["Long", "Short"]},
    ]

    with patch.object(app_module, "initialize_session", return_value=mock_agent):
        with api_client.session_transaction() as sess:
            sess["user_id"] = "u1"
            sess["username"] = "u"
        resp = api_client.post(
            "/popup_start",
            data={"ticker": "AAPL", "trade_type": "Investment"},
        )

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["questions"][0]["question"] == "Goal?"
    assert "session_id" in data
    assert "subjects" in data
    mock_agent.reset_conversation.assert_called_once()
    mock_agent.start_research.assert_called_once_with("AAPL", "Investment")


def test_start_generation_returns_success_and_schedules_thread(api_client):
    import app as app_module

    mock_agent = MagicMock()
    mock_thread = MagicMock()

    with patch.object(app_module, "initialize_session", return_value=mock_agent):
        with patch.object(app_module, "get_or_create_session_id", return_value="sid-gen"):
            with patch("spend_budget.get_spend_budget_usd", return_value=2.5):
                with patch.object(app_module.threading, "Thread", return_value=mock_thread):
                    with api_client.session_transaction() as sess:
                        sess["user_id"] = "u1"
                        sess["username"] = "nu"
                    resp = api_client.post(
                        "/start_generation",
                        json={"questions": ["Q?"], "answers": ["A"]},
                        content_type="application/json",
                    )

    assert resp.status_code == 200
    assert resp.get_json() == {"success": True}
    assert mock_agent.user_id == "u1"
    assert mock_agent.username == "nu"
    mock_thread.start.assert_called_once()
