"""Tests for ticker-centric report page and notes save route."""

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
    flask_app.config["SECRET_KEY"] = "test-ticker-notes"
    return flask_app


@pytest.fixture
def api_client(api_app):
    return api_app.test_client()


def test_ticker_page_requires_auth(api_client):
    resp = api_client.get("/ticker/AAPL")
    assert resp.status_code == 302
    assert "/sign-in" in (resp.headers.get("Location") or "")


def test_ticker_page_renders_reports_and_notes(api_client):
    import app as app_module

    mock_storage = MagicMock()
    mock_storage.get_all_reports.return_value = (
        [
            {
                "report_id": "r1",
                "ticker": "AAPL",
                "trade_type": "Investment",
                "report_text": "Body",
                "created_at": None,
            }
        ],
        1,
    )
    mock_db = MagicMock()
    mock_db.get_ticker_notes.return_value = [
        {
            "id": 1,
            "title": "Thesis",
            "content": "<p>Existing thesis note</p>",
            "created_at": None,
        }
    ]

    with patch.object(app_module, "ReportStorage", return_value=mock_storage):
        with patch("database.get_database_manager", return_value=mock_db):
            with api_client.session_transaction() as sess:
                sess["user_id"] = "u1"
                sess["username"] = "tester"
            resp = api_client.get("/ticker/AAPL")

    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "AAPL Research" in html
    assert "Existing thesis note" in html


def test_save_ticker_notes_persists_content(api_client):
    mock_db = MagicMock()
    with patch("database.get_database_manager", return_value=mock_db):
        with api_client.session_transaction() as sess:
            sess["user_id"] = "u1"
            sess["username"] = "tester"
        resp = api_client.post("/ticker/AAPL/notes", data={"content": "<p>My note</p>"})

    assert resp.status_code == 302
    mock_db.create_ticker_note.assert_called_once()
    call_args = mock_db.create_ticker_note.call_args[0]
    assert call_args[0] == "u1"
    assert call_args[1] == "AAPL"
    assert "My note" in call_args[3]

