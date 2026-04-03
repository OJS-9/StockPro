"""Public auth pages and auth-aware '/' home."""

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
    flask_app.config["SECRET_KEY"] = "test-public-pages"
    return flask_app


@pytest.fixture
def api_client(api_app):
    return api_app.test_client()


class TestPublicAuthPages:
    def test_sign_in_renders(self, api_client):
        resp = api_client.get("/sign-in")
        assert resp.status_code == 200

    def test_sign_up_renders(self, api_client):
        resp = api_client.get("/sign-up")
        assert resp.status_code == 200

    def test_auth_sso_callback_renders(self, api_client):
        resp = api_client.get("/auth/sso-callback")
        assert resp.status_code == 200


class TestIndexAuth:
    def test_root_renders_anonymous_public_home(self, api_client):
        resp = api_client.get("/")
        assert resp.status_code == 200
        assert b"Join the waitlist" in resp.data

    def test_root_renders_when_logged_in(self, api_client):
        import app as app_module

        mock_wl = MagicMock()
        mock_wl.get_pinned_tickers.return_value = None
        with patch.object(app_module, "get_watchlist_service", return_value=mock_wl):
            with api_client.session_transaction() as sess:
                sess["user_id"] = "u1"
                sess["username"] = "user1"
            resp = api_client.get("/")
        assert resp.status_code == 200

    def test_login_compat_redirects_to_sign_in(self, api_client):
        resp = api_client.get("/login")
        assert resp.status_code == 302
        assert "/sign-in" in (resp.headers.get("Location") or "")
