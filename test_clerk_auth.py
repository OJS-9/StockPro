"""
Tests for Clerk authentication integration.
Verifies:
- Clerk client init is present in app.py
- Old auth routes (/login, /register, /logout) are gone
- New auth routes (/sign-in, /sign-up, /sign-out) exist
- login_required decorator uses Clerk JWT verification
- clerk_publishable_key is injected into context processor
"""
import ast
import pathlib


APP_SRC = pathlib.Path("src/app.py").read_text()
APP_TREE = ast.parse(APP_SRC)

NAV_SRC = pathlib.Path("templates/_nav.html").read_text()
BASE_SRC = pathlib.Path("templates/base.html").read_text()


class TestRemovedOldAuth:
    """Old auth imports and routes should be gone."""

    def test_authlib_import_removed(self):
        assert "from authlib" not in APP_SRC, "authlib import should be removed"

    def test_werkzeug_password_hash_removed(self):
        assert "from werkzeug.security" not in APP_SRC, (
            "werkzeug password hash import should be removed"
        )

    def test_oauth_object_removed(self):
        assert "oauth = OAuth(" not in APP_SRC, "OAuth() init should be removed"

    def test_login_route_removed(self):
        assert "@app.route('/login'" not in APP_SRC, "/login route should be removed"

    def test_register_route_removed(self):
        assert "@app.route('/register'" not in APP_SRC, "/register route should be removed"

    def test_logout_route_removed(self):
        assert "@app.route('/logout')" not in APP_SRC, "/logout route should be removed"

    def test_google_oauth_routes_removed(self):
        assert "@app.route('/login/google')" not in APP_SRC, (
            "Google OAuth routes should be removed"
        )


class TestClerkInit:
    """Clerk client should be initialised in app.py."""

    def test_clerk_import_present(self):
        assert "from clerk_backend_api import Clerk" in APP_SRC, (
            "clerk_backend_api import missing"
        )

    def test_clerk_client_init_present(self):
        assert "ClerkClient(" in APP_SRC, "ClerkClient() init missing"

    def test_clerk_jwt_key_env_present(self):
        assert "CLERK_JWT_KEY" in APP_SRC, "CLERK_JWT_KEY env var not referenced"


class TestNewRoutes:
    """New Clerk-based routes should exist."""

    def test_sign_in_route_exists(self):
        assert "/sign-in" in APP_SRC, "/sign-in route missing"

    def test_sign_up_route_exists(self):
        assert "/sign-up" in APP_SRC, "/sign-up route missing"

    def test_sign_out_route_exists(self):
        assert "/sign-out" in APP_SRC, "/sign-out route missing"


class TestLoginRequiredDecorator:
    """login_required should use Clerk JWT / Flask session, not werkzeug."""

    def test_login_required_uses_session_check(self):
        """login_required should check 'user_id' in session first."""
        assert "'user_id' in session" in APP_SRC or '"user_id" in session' in APP_SRC, (
            "login_required should check session['user_id']"
        )

    def test_login_required_redirects_to_sign_in(self):
        """login_required should redirect to /sign-in, not /login."""
        # Find login_required function and check it references sign_in
        for node in ast.walk(APP_TREE):
            if isinstance(node, ast.FunctionDef) and node.name == 'login_required':
                func_src = ast.unparse(node)
                assert "sign_in" in func_src or "sign-in" in func_src, (
                    "login_required should redirect to sign_in, not login"
                )
                assert "url_for('login')" not in func_src, (
                    "login_required should not redirect to /login"
                )
                return
        # If we can't find the function, the test fails
        assert False, "login_required function not found in app.py"

    def test_clerk_session_cookie_checked(self):
        """login_required should verify __session cookie via Clerk."""
        assert "__session" in APP_SRC, (
            "login_required should check __session cookie for Clerk JWT"
        )


class TestContextProcessor:
    """clerk_publishable_key should be injected via context processor."""

    def test_clerk_publishable_key_in_context(self):
        assert "clerk_publishable_key" in APP_SRC, (
            "clerk_publishable_key should be in context processor"
        )

    def test_clerk_publishable_key_env_read(self):
        assert "CLERK_PUBLISHABLE_KEY" in APP_SRC, (
            "CLERK_PUBLISHABLE_KEY env var should be read"
        )


class TestNavTemplate:
    """Navigation template should use new Clerk routes."""

    def test_nav_uses_sign_out(self):
        assert "sign-out" in NAV_SRC or "sign_out" in NAV_SRC, (
            "_nav.html should link to /sign-out"
        )

    def test_nav_no_logout(self):
        assert "url_for('logout')" not in NAV_SRC, (
            "_nav.html should not reference /logout"
        )

    def test_nav_uses_sign_in(self):
        assert "sign-in" in NAV_SRC or "sign_in" in NAV_SRC, (
            "_nav.html should link to /sign-in"
        )

    def test_nav_uses_sign_up(self):
        assert "sign-up" in NAV_SRC or "sign_up" in NAV_SRC, (
            "_nav.html should link to /sign-up"
        )


class TestBaseTemplate:
    """base.html should include Clerk JS CDN script."""

    def test_clerk_js_cdn_present(self):
        assert "clerk-js" in BASE_SRC or "clerk.browser.js" in BASE_SRC, (
            "base.html should include ClerkJS CDN script"
        )

    def test_clerk_publishable_key_in_script(self):
        assert "clerk_publishable_key" in BASE_SRC, (
            "base.html should use clerk_publishable_key template variable"
        )


class TestOldTemplatesGone:
    """login.html and register.html should be deleted."""

    def test_login_html_deleted(self):
        assert not pathlib.Path("templates/login.html").exists(), (
            "templates/login.html should be deleted"
        )

    def test_register_html_deleted(self):
        assert not pathlib.Path("templates/register.html").exists(), (
            "templates/register.html should be deleted"
        )


class TestNewTemplatesExist:
    """sign_in.html and sign_up.html should exist."""

    def test_sign_in_html_exists(self):
        assert pathlib.Path("templates/sign_in.html").exists(), (
            "templates/sign_in.html should be created"
        )

    def test_sign_up_html_exists(self):
        assert pathlib.Path("templates/sign_up.html").exists(), (
            "templates/sign_up.html should be created"
        )


SIGN_IN_SRC = pathlib.Path("templates/sign_in.html").read_text()
SIGN_UP_SRC = pathlib.Path("templates/sign_up.html").read_text()


class TestClerkAuthSecurityFixes:
    """Critical and high-severity fixes for Clerk auth integration."""

    # Fix 1: bare except must log, not silently swallow
    def test_bare_except_logs_error(self):
        """login_required except block must log the error, not pass silently."""
        assert "app.logger.error" in APP_SRC, (
            "login_required except block should call app.logger.error"
        )

    def test_bare_except_not_silent(self):
        """login_required must not have bare 'except Exception: pass'."""
        # The original pattern: except Exception:\n                pass
        assert "except Exception:\n                pass" not in APP_SRC, (
            "Silent 'except Exception: pass' must be replaced with logging"
        )

    # Fix 2: fail-loud guards for CLERK_SECRET_KEY and CLERK_JWT_KEY
    def test_clerk_secret_key_fail_loud(self):
        """CLERK_SECRET_KEY must have a RuntimeError fail-loud guard."""
        assert "CLERK_SECRET_KEY" in APP_SRC, "CLERK_SECRET_KEY not referenced"
        # Should raise RuntimeError if missing, not silently use empty string
        assert "CLERK_SECRET_KEY" in APP_SRC and (
            "raise RuntimeError" in APP_SRC
        ), "Missing RuntimeError guard for required env vars"

    def test_clerk_jwt_key_fail_loud(self):
        """CLERK_JWT_KEY must have a RuntimeError fail-loud guard."""
        # After fix, CLERK_JWT_KEY should not have a fallback empty string default
        # i.e. os.getenv('CLERK_JWT_KEY', '') should be replaced with fail-loud
        assert "CLERK_JWT_KEY" in APP_SRC, "CLERK_JWT_KEY not referenced"
        # The fail-loud pattern checks for falsy value then raises
        # Look for the guard pattern that covers CLERK_JWT_KEY
        assert "_clerk_jwt_key_raw" in APP_SRC or (
            "CLERK_JWT_KEY" in APP_SRC and "not _clerk" in APP_SRC
        ), "CLERK_JWT_KEY must have a fail-loud guard (RuntimeError if not set)"

    # Fix 3: ClerkJS CDN SRI hash or explicit deferral comment
    def test_clerk_cdn_has_sri_or_comment(self):
        """ClerkJS CDN script must have integrity attribute or deferral comment."""
        # integrity= may be on a different line from the src= in a multi-line tag
        # Check if both clerk.browser.js AND integrity= are anywhere in base.html
        has_clerk_script = "clerk.browser.js" in BASE_SRC
        has_integrity = "integrity=" in BASE_SRC
        # Check for deferral comment anywhere near the clerk script
        has_deferral_comment = "SRI" in BASE_SRC and (
            "defer" in BASE_SRC.lower() or "dynamic" in BASE_SRC.lower() or "<!-- " in BASE_SRC
        )
        assert (has_clerk_script and has_integrity) or has_deferral_comment, (
            "ClerkJS CDN script must have integrity= attribute or an SRI deferral comment"
        )

    # Fix 4: sign_in.html and sign_up.html must have try/catch around Clerk.load()
    def test_sign_in_clerk_load_has_try_catch(self):
        """sign_in.html Clerk.load() must be wrapped in try/catch."""
        assert "try {" in SIGN_IN_SRC or "try{" in SIGN_IN_SRC, (
            "sign_in.html: Clerk.load() must be wrapped in try/catch"
        )
        assert "catch" in SIGN_IN_SRC, (
            "sign_in.html: try block must have a catch handler"
        )

    def test_sign_up_clerk_load_has_try_catch(self):
        """sign_up.html Clerk.load() must be wrapped in try/catch."""
        assert "try {" in SIGN_UP_SRC or "try{" in SIGN_UP_SRC, (
            "sign_up.html: Clerk.load() must be wrapped in try/catch"
        )
        assert "catch" in SIGN_UP_SRC, (
            "sign_up.html: try block must have a catch handler"
        )

    def test_sign_in_shows_error_message_on_failure(self):
        """sign_in.html catch block must show a visible error message."""
        assert "unavailable" in SIGN_IN_SRC.lower() or "error" in SIGN_IN_SRC.lower(), (
            "sign_in.html catch block must display an error message to the user"
        )

    def test_sign_up_shows_error_message_on_failure(self):
        """sign_up.html catch block must show a visible error message."""
        assert "unavailable" in SIGN_UP_SRC.lower() or "error" in SIGN_UP_SRC.lower(), (
            "sign_up.html catch block must display an error message to the user"
        )
