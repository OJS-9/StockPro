"""Phase 1: JSON API route tests (report status, reports AJAX, public news)."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent / "src"))


@pytest.fixture
def api_app():
    from app import app as flask_app

    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False
    flask_app.config["SECRET_KEY"] = "test-api-secret"
    return flask_app


@pytest.fixture
def api_client(api_app):
    return api_app.test_client()


class TestReportStatusApi:
    def test_forbidden_when_session_id_mismatch(self, api_client):
        import app as app_module

        with patch.object(
            app_module,
            "_generation_status",
            {"good-sid": {"status": "ready", "report_id": "r1"}},
        ):
            with api_client.session_transaction() as sess:
                sess["user_id"] = "u1"
                sess["session_id"] = "good-sid"
            resp = api_client.get("/api/report_status/wrong-sid")
            assert resp.status_code == 403
            assert resp.get_json() == {"error": "forbidden"}

    def test_returns_status_when_session_matches(self, api_client):
        import app as app_module

        payload = {"status": "ready", "report_id": "r1"}
        with patch.object(app_module, "_generation_status", {"good-sid": payload}):
            with api_client.session_transaction() as sess:
                sess["user_id"] = "u1"
                sess["session_id"] = "good-sid"
            resp = api_client.get("/api/report_status/good-sid")
            assert resp.status_code == 200
            assert resp.get_json() == payload


class TestApiReportsAuth:
    def test_redirects_when_not_logged_in(self, api_client):
        resp = api_client.get("/api/reports")
        assert resp.status_code == 302
        assert "/sign-in" in (resp.headers.get("Location") or "")

    def test_success_json_when_logged_in(self, api_client):
        import app as app_module

        with patch.object(app_module, "ReportStorage") as MockStorage:
            instance = MockStorage.return_value
            instance.get_all_reports.return_value = ([], 0)
            with api_client.session_transaction() as sess:
                sess["user_id"] = "user-x"
            resp = api_client.get("/api/reports")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert data["reports"] == []
            assert data["total_count"] == 0
            assert data["current_page"] == 1


class TestApiNewsPublic:
    def test_api_news_returns_json_list(self, api_client):
        with patch("news_service.get_briefing", return_value=[]):
            resp = api_client.get("/api/news")
            assert resp.status_code == 200
            assert resp.get_json() == []
