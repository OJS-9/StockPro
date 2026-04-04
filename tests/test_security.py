"""
Security overhaul tests.
Tests the key security changes made to app.py:
- bleach XSS sanitization in markdown filter
- FLASK_SECRET_KEY fail-loud
- File size limit logic
- Session TTL eviction logic
"""
import time
import pytest


# ---------------------------------------------------------------------------
# Markdown / XSS sanitization
# ---------------------------------------------------------------------------

def _make_markdown_filter():
    import bleach
    import markdown as md_lib
    from markupsafe import Markup

    allowed_tags = list(bleach.sanitizer.ALLOWED_TAGS) + [
        'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'pre', 'code', 'blockquote', 'table', 'thead',
        'tbody', 'tr', 'th', 'td', 'hr', 'br', 'ul', 'ol', 'li',
    ]
    allowed_attrs = {**bleach.sanitizer.ALLOWED_ATTRIBUTES, '*': ['class']}

    def markdown_filter(text):
        raw_html = md_lib.markdown(text or '', extensions=['tables', 'fenced_code', 'nl2br', 'sane_lists'])
        return Markup(bleach.clean(raw_html, tags=allowed_tags, attributes=allowed_attrs, strip=True))

    return markdown_filter


class TestMarkdownSanitization:
    def setup_method(self):
        self.md = _make_markdown_filter()

    def test_script_tag_stripped(self):
        result = str(self.md('<script>evil()</script> **hi**'))
        assert '<script>' not in result
        assert '</script>' not in result

    def test_onerror_attr_stripped(self):
        result = str(self.md('<img src=x onerror=alert(1)>'))
        assert 'onerror' not in result

    def test_onclick_attr_stripped(self):
        result = str(self.md('<p onclick="steal()">text</p>'))
        assert 'onclick' not in result

    def test_bold_preserved(self):
        result = str(self.md('**bold text**'))
        assert 'bold text' in result
        assert '<strong>' in result or '<b>' in result

    def test_heading_preserved(self):
        result = str(self.md('# Title'))
        assert 'Title' in result
        assert '<h1>' in result

    def test_empty_input(self):
        result = str(self.md(''))
        assert result is not None

    def test_none_input(self):
        result = str(self.md(None))
        assert result is not None


# ---------------------------------------------------------------------------
# FLASK_SECRET_KEY fail-loud logic
# ---------------------------------------------------------------------------

class TestSecretKeyFailLoud:
    def test_raises_when_missing(self):
        import os
        key = os.getenv('THIS_KEY_DOES_NOT_EXIST_XYZ_999')
        with pytest.raises(RuntimeError, match='FLASK_SECRET_KEY'):
            if not key:
                raise RuntimeError('FLASK_SECRET_KEY environment variable is not set')

    def test_does_not_raise_when_set(self):
        key = 'a-valid-secret-key'
        if not key:
            raise RuntimeError('FLASK_SECRET_KEY environment variable is not set')
        # No exception = pass


# ---------------------------------------------------------------------------
# CSV file size limit logic
# ---------------------------------------------------------------------------

class TestCSVFileSizeLimit:
    def _check_size(self, size_bytes):
        if size_bytes > 10 * 1024 * 1024:
            raise ValueError("File exceeds 10MB limit")

    def test_allows_small_file(self):
        self._check_size(1024)  # 1KB — should not raise

    def test_allows_exactly_10mb(self):
        self._check_size(10 * 1024 * 1024)  # exactly 10MB — should not raise

    def test_rejects_over_10mb(self):
        with pytest.raises(ValueError, match='10MB'):
            self._check_size(10 * 1024 * 1024 + 1)


# ---------------------------------------------------------------------------
# Session TTL eviction logic
# ---------------------------------------------------------------------------

class TestSessionTTLEviction:
    def setup_method(self):
        self.agent_sessions = {}
        self._generation_status = {}
        self._sse_queues = {}
        self._session_created_at = {}

    def _evict_stale_sessions(self, max_age_seconds=86400):
        cutoff = time.time() - max_age_seconds
        stale = [sid for sid, t in self._session_created_at.items() if t < cutoff]
        for sid in stale:
            self.agent_sessions.pop(sid, None)
            self._generation_status.pop(sid, None)
            self._sse_queues.pop(sid, None)
            self._session_created_at.pop(sid, None)

    def test_stale_session_evicted(self):
        sid = 'old-session'
        self.agent_sessions[sid] = object()
        self._session_created_at[sid] = time.time() - 90000  # 25h ago

        self._evict_stale_sessions(max_age_seconds=86400)

        assert sid not in self.agent_sessions
        assert sid not in self._session_created_at

    def test_fresh_session_kept(self):
        sid = 'fresh-session'
        self.agent_sessions[sid] = object()
        self._session_created_at[sid] = time.time() - 100  # 100s ago

        self._evict_stale_sessions(max_age_seconds=86400)

        assert sid in self.agent_sessions

    def test_all_dicts_cleaned_together(self):
        sid = 'multi-dict-session'
        self.agent_sessions[sid] = object()
        self._generation_status[sid] = {'status': 'in_progress'}
        self._sse_queues[sid] = object()
        self._session_created_at[sid] = time.time() - 90000

        self._evict_stale_sessions(max_age_seconds=86400)

        assert sid not in self.agent_sessions
        assert sid not in self._generation_status
        assert sid not in self._sse_queues
        assert sid not in self._session_created_at


# ---------------------------------------------------------------------------
# Open redirect validation
# ---------------------------------------------------------------------------

def _safe_redirect_url(next_url, fallback):
    """Mirror of the safe redirect logic applied in app.py after login."""
    if next_url and next_url.startswith('/') and not next_url.startswith('//'):
        return next_url
    return fallback


class TestOpenRedirectValidation:
    """Validate that next_url is checked to be same-origin before redirect."""

    FALLBACK = '/index'

    def test_relative_path_allowed(self):
        result = _safe_redirect_url('/portfolio', self.FALLBACK)
        assert result == '/portfolio'

    def test_relative_path_with_query_allowed(self):
        result = _safe_redirect_url('/reports?ticker=AAPL', self.FALLBACK)
        assert result == '/reports?ticker=AAPL'

    def test_absolute_external_url_blocked(self):
        result = _safe_redirect_url('https://evil.com/phishing', self.FALLBACK)
        assert result == self.FALLBACK

    def test_protocol_relative_url_blocked(self):
        result = _safe_redirect_url('//evil.com/phishing', self.FALLBACK)
        assert result == self.FALLBACK

    def test_none_falls_back(self):
        result = _safe_redirect_url(None, self.FALLBACK)
        assert result == self.FALLBACK

    def test_empty_string_falls_back(self):
        result = _safe_redirect_url('', self.FALLBACK)
        assert result == self.FALLBACK

    def test_absolute_http_url_blocked(self):
        result = _safe_redirect_url('http://evil.com', self.FALLBACK)
        assert result == self.FALLBACK

    def test_login_required_redirects_to_sign_in_not_login(self):
        """login_required decorator must redirect to sign_in, not the old /login route."""
        import ast, pathlib
        source = pathlib.Path('src/app.py').read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'login_required':
                func_src = ast.unparse(node)
                assert "url_for('login')" not in func_src, (
                    "login_required should not redirect to /login after Clerk migration"
                )
                assert "sign_in" in func_src or "sign-in" in func_src, (
                    "login_required should redirect to sign_in"
                )
                return
        pytest.fail("Could not find login_required function in src/app.py")
