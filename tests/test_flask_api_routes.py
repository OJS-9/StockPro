"""Phase 1: JSON API route tests (report status, reports AJAX, public news)."""

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


class TestPortfolioApiJson:
    def test_portfolio_prices_404_when_not_owner(self, api_client):
        import app as app_module

        mock_svc = MagicMock()
        mock_svc.get_portfolio.return_value = {
            "portfolio_id": "p1",
            "user_id": "someone-else",
        }
        with patch.object(app_module, "get_portfolio_service", return_value=mock_svc):
            with api_client.session_transaction() as sess:
                sess["user_id"] = "me"
            resp = api_client.get("/api/portfolio/p1/prices")
        assert resp.status_code == 404
        assert resp.get_json() == {"error": "Not found"}

    def test_portfolio_prices_returns_holdings_when_owner(self, api_client):
        import app as app_module

        mock_svc = MagicMock()
        mock_svc.get_portfolio.return_value = {"portfolio_id": "p1", "user_id": "me"}
        mock_svc.get_allocation_breakdowns_from_summary.return_value = {
            "prices_loaded": True,
            "sector": [{"label": "Technology", "value": 1000.0, "pct": 100.0}],
            "market": [{"label": "US Stocks", "value": 1000.0, "pct": 100.0}],
        }
        mock_svc.get_portfolio_summary.return_value = {
            "prices_loaded": True,
            "holdings": [
                {
                    "symbol": "AAPL",
                    "price_available": True,
                    "current_price": 100.0,
                    "market_value": 1000.0,
                    "unrealized_gain": 10.0,
                    "unrealized_gain_pct": 1.0,
                }
            ],
            "total_market_value": 1000.0,
            "total_unrealized_gain": 10.0,
            "total_unrealized_gain_pct": 1.0,
            "stock_allocation_pct": 100.0,
            "crypto_allocation_pct": 0.0,
            "cash_allocation_pct": 0.0,
        }
        with patch.object(app_module, "get_portfolio_service", return_value=mock_svc):
            with api_client.session_transaction() as sess:
                sess["user_id"] = "me"
            resp = api_client.get("/api/portfolio/p1/prices")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["holdings"][0]["symbol"] == "AAPL"
        assert data["total_market_value"] == 1000.0
        assert data["breakdowns"]["sector"][0]["label"] == "Technology"
        assert data["breakdowns"]["market"][0]["label"] == "US Stocks"

    def test_portfolios_prices_returns_list_per_portfolio(self, api_client):
        import app as app_module

        mock_svc = MagicMock()
        mock_svc.list_portfolios.return_value = [{"portfolio_id": "p1"}]
        mock_svc.get_portfolio_summary.return_value = {
            "total_market_value": 100.0,
            "total_unrealized_gain": 5.0,
            "total_unrealized_gain_pct": 5.0,
        }
        with patch.object(app_module, "get_portfolio_service", return_value=mock_svc):
            with api_client.session_transaction() as sess:
                sess["user_id"] = "me"
            resp = api_client.get("/api/portfolios/prices")
        assert resp.status_code == 200
        rows = resp.get_json()
        assert len(rows) == 1
        assert rows[0]["portfolio_id"] == "p1"
        assert rows[0]["total_market_value"] == 100.0

    def test_portfolio_history_404_when_not_owner(self, api_client):
        import app as app_module

        mock_svc = MagicMock()
        mock_svc.get_portfolio.return_value = {
            "portfolio_id": "p1",
            "user_id": "other",
        }
        with patch.object(app_module, "get_portfolio_service", return_value=mock_svc):
            with api_client.session_transaction() as sess:
                sess["user_id"] = "me"
            resp = api_client.get("/api/portfolio/p1/history")
        assert resp.status_code == 404

    def test_portfolio_history_returns_json_when_owner(self, api_client):
        import app as app_module

        mock_portfolio = MagicMock()
        mock_portfolio.get_portfolio.return_value = {
            "portfolio_id": "p1",
            "user_id": "me",
        }
        mock_history = MagicMock()
        mock_history.get_monthly_values.return_value = {"months": [], "values": []}

        with patch.object(app_module, "get_portfolio_service", return_value=mock_portfolio):
            with patch.object(app_module, "get_history_service", return_value=mock_history):
                with api_client.session_transaction() as sess:
                    sess["user_id"] = "me"
                resp = api_client.get("/api/portfolio/p1/history")
        assert resp.status_code == 200
        assert resp.get_json() == {"months": [], "values": []}


class TestTelegramLinkingApi:
    def test_connect_token_requires_login(self, api_client):
        resp = api_client.get("/api/telegram/connect-token")
        assert resp.status_code == 302
        assert "/sign-in" in (resp.headers.get("Location") or "")

    def test_connect_token_returns_token_when_logged_in(self, api_client):
        import app as app_module

        mock_db = MagicMock()
        mock_db.create_telegram_connect_token.return_value = "tok-123"
        with patch("database.get_database_manager", return_value=mock_db):
            with api_client.session_transaction() as sess:
                sess["user_id"] = "me"
            resp = api_client.get("/api/telegram/connect-token")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["token"] == "tok-123"
