"""Free-tier monthly report quota (STOA-22)."""

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
    flask_app.config["SECRET_KEY"] = "test-report-usage"
    return flask_app


@pytest.fixture
def api_client(api_app):
    return api_app.test_client()


def test_start_generation_403_when_quota_exceeded(api_client):
    import app as app_module

    with patch.object(app_module, "_session_hits_report_quota", return_value=True):
        with api_client.session_transaction() as sess:
            sess["user_id"] = "u1"
            sess["username"] = "u"
        resp = api_client.post(
            "/start_generation",
            json={"questions": []},
            content_type="application/json",
        )

    assert resp.status_code == 403
    assert resp.get_json()["error"] == "limit_reached"
    assert "free reports" in resp.get_json()["message"].lower()


def test_start_generation_proceeds_when_quota_ok(api_client):
    import app as app_module

    mock_agent = MagicMock()
    mock_thread = MagicMock()

    with patch.object(app_module, "_session_hits_report_quota", return_value=False):
        with patch.object(app_module, "initialize_session", return_value=mock_agent):
            with patch.object(app_module, "get_or_create_session_id", return_value="sid"):
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


def test_api_usage_returns_counts(api_client):
    mock_db = MagicMock()
    mock_db.user_is_pro.return_value = False
    mock_db.get_report_usage_count.return_value = 2

    with patch("database.get_database_manager", return_value=mock_db):
        with patch("report_usage.current_period_month", return_value="2026-03"):
            with patch("report_usage.get_free_tier_report_limit", return_value=3):
                with api_client.session_transaction() as sess:
                    sess["user_id"] = "u1"
                resp = api_client.get("/api/usage")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["reports_used"] == 2
    assert data["reports_limit"] == 3
    assert data["period"] == "2026-03"
    assert data["is_pro"] is False


def test_quota_exceeded_for_user_resets_in_new_period():
    from report_usage import quota_exceeded_for_user

    db = MagicMock()
    db.user_is_pro.return_value = False
    db.get_report_usage_count.side_effect = lambda uid, p: 3 if p == "2026-03" else 0

    exceeded_march, _, used_m = quota_exceeded_for_user(db, "u1", period="2026-03")
    assert exceeded_march is True
    assert used_m == 3

    exceeded_april, _, used_a = quota_exceeded_for_user(db, "u1", period="2026-04")
    assert exceeded_april is False
    assert used_a == 0


def test_store_report_increments_usage_when_user_id():
    from report_storage import ReportStorage

    storage = ReportStorage.__new__(ReportStorage)
    mock_db = MagicMock()
    mock_db.save_report.return_value = "rid-1"
    storage._db = mock_db
    storage.chunker = MagicMock()
    storage.chunker.chunk_report.return_value = [
        {"chunk_text": "hello", "chunk_index": 0, "section": None}
    ]
    storage.embedding_service = MagicMock()
    storage.embedding_service.create_embeddings_batch.return_value = [[0.1]]

    rid = storage.store_report(
        "AAPL",
        "Investment",
        "full report text",
        metadata={"x": 1},
        user_id="user-1",
    )

    assert rid == "rid-1"
    mock_db.increment_report_usage.assert_called_once_with("user-1")


def test_store_report_skips_increment_without_user_id():
    from report_storage import ReportStorage

    storage = ReportStorage.__new__(ReportStorage)
    mock_db = MagicMock()
    mock_db.save_report.return_value = "rid-2"
    storage._db = mock_db
    storage.chunker = MagicMock()
    storage.chunker.chunk_report.return_value = [
        {"chunk_text": "hello", "chunk_index": 0, "section": None}
    ]
    storage.embedding_service = MagicMock()
    storage.embedding_service.create_embeddings_batch.return_value = [[0.1]]

    storage.store_report("AAPL", "Investment", "text", user_id=None)

    mock_db.increment_report_usage.assert_not_called()
