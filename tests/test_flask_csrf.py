"""
Phase 1: CSRF protection regression tests.

Ensures state-changing POST routes reject missing tokens when WTF_CSRF_ENABLED is True.
Other tests disable CSRF for convenience; these explicitly enable it.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "src"))


def _extract_csrf_from_html(html: str) -> str:
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    if not m:
        m = re.search(r'value="([^"]+)"\s+name="csrf_token"', html)
    assert m, "expected hidden csrf_token input in HTML"
    return m.group(1)


@pytest.fixture
def app_csrf():
    """Flask app with CSRF on; TESTING skips Flask-Limiter (see app._skip_rate_limits_in_tests)."""
    from app import app as flask_app

    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = True
    flask_app.config["SECRET_KEY"] = "test-csrf-secret-phase1"
    return flask_app


@pytest.fixture
def client_csrf(app_csrf):
    return app_csrf.test_client()


@pytest.fixture
def logged_in_csrf(client_csrf):
    with client_csrf.session_transaction() as sess:
        sess["user_id"] = "csrf-test-user"
        sess["username"] = "csrfuser"
    return client_csrf


class TestCsrfProtection:
    def test_post_clear_without_csrf_returns_400(self, logged_in_csrf):
        resp = logged_in_csrf.post("/clear", data={})
        assert resp.status_code == 400

    def test_post_clear_with_token_from_chat_page_redirects(self, app_csrf, logged_in_csrf):
        page = logged_in_csrf.get("/chat")
        assert page.status_code == 200
        token = _extract_csrf_from_html(page.get_data(as_text=True))
        resp = logged_in_csrf.post("/clear", data={"csrf_token": token})
        assert resp.status_code in (302, 303)
        assert "/chat" in (resp.headers.get("Location") or "")
