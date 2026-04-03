"""Phase 1: Watchlist Flask routes — auth, ownership (403), create redirect."""

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
    flask_app.config["SECRET_KEY"] = "test-watchlist-secret"
    return flask_app


@pytest.fixture
def api_client(api_app):
    return api_app.test_client()


class TestWatchlistRoutesAuth:
    def test_watchlist_redirects_when_not_logged_in(self, api_client):
        resp = api_client.get("/watchlist")
        assert resp.status_code == 302
        assert "/sign-in" in (resp.headers.get("Location") or "")

    def test_watchlist_renders_when_logged_in(self, api_client):
        import app as app_module

        mock_svc = MagicMock()
        mock_svc.list_watchlists.return_value = [
            {"watchlist_id": "wl-1", "name": "Main", "user_id": "me"}
        ]
        mock_svc.db.get_watchlist.return_value = {
            "watchlist_id": "wl-1",
            "user_id": "me",
            "name": "Main",
        }
        mock_svc.get_watchlist_with_items.return_value = {
            "watchlist_id": "wl-1",
            "items": [],
        }

        with patch.object(app_module, "get_watchlist_service", return_value=mock_svc):
            with api_client.session_transaction() as sess:
                sess["user_id"] = "me"
                sess["username"] = "testuser"
            resp = api_client.get("/watchlist")
        assert resp.status_code == 200
        assert b"stockpro-alerts-root" in resp.data


class TestWatchlistOwnershipPost:
    def test_rename_aborts_403_for_other_users_watchlist(self, api_client):
        import app as app_module

        mock_svc = MagicMock()
        mock_svc.db.get_watchlist.return_value = {
            "watchlist_id": "wl-x",
            "user_id": "other",
        }
        with patch.object(app_module, "get_watchlist_service", return_value=mock_svc):
            with api_client.session_transaction() as sess:
                sess["user_id"] = "me"
            resp = api_client.post(
                "/watchlist/wl-x/rename",
                data={"name": "New Name"},
            )
        assert resp.status_code == 403

    def test_add_symbol_aborts_403_for_other_users_watchlist(self, api_client):
        import app as app_module

        mock_svc = MagicMock()
        mock_svc.db.get_watchlist.return_value = {
            "watchlist_id": "wl-x",
            "user_id": "other",
        }
        with patch.object(app_module, "get_watchlist_service", return_value=mock_svc):
            with api_client.session_transaction() as sess:
                sess["user_id"] = "me"
            resp = api_client.post(
                "/watchlist/wl-x/add-symbol",
                data={"symbol": "AAPL"},
            )
        assert resp.status_code == 403


class TestWatchlistCreate:
    def test_create_redirects_and_calls_service(self, api_client):
        import app as app_module

        mock_svc = MagicMock()
        mock_svc.create_watchlist.return_value = "new-wl-id"
        with patch.object(app_module, "get_watchlist_service", return_value=mock_svc):
            with api_client.session_transaction() as sess:
                sess["user_id"] = "me"
            resp = api_client.post(
                "/watchlist/create",
                data={"name": "Secondary"},
                follow_redirects=False,
            )
        assert resp.status_code == 302
        mock_svc.create_watchlist.assert_called_once_with("me", "Secondary")
