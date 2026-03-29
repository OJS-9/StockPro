"""
TDD tests for _warm_portfolio_cache helper and login_required thread spawn.
"""
import sys
import os
import threading
import time
import unittest
from unittest.mock import MagicMock, patch, call

# Add src to path so we can import from app.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))


class TestWarmPortfolioCache(unittest.TestCase):
    """Tests for the _warm_portfolio_cache helper function."""

    def test_warm_portfolio_cache_exists_in_app(self):
        """_warm_portfolio_cache must exist as a callable in src/app.py module-level."""
        import importlib
        # We import only the function — avoid full Flask app initialization
        import ast
        app_path = os.path.join(os.path.dirname(__file__), 'src', 'app.py')
        with open(app_path) as f:
            tree = ast.parse(f.read())
        func_names = [
            node.name for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
        ]
        self.assertIn('_warm_portfolio_cache', func_names,
                      "_warm_portfolio_cache function not found in src/app.py")

    def test_warm_portfolio_cache_fetches_holdings_for_all_portfolios(self):
        """_warm_portfolio_cache calls db.get_holdings(portfolio_id) for each portfolio."""
        mock_svc = MagicMock()
        mock_svc.list_portfolios.return_value = [
            {'portfolio_id': '1'}, {'portfolio_id': '2'}
        ]
        mock_svc.db.get_holdings.return_value = []

        with patch('portfolio.portfolio_service.get_portfolio_service', return_value=mock_svc):
            # Import the function from app source without triggering Flask app
            import ast
            import types
            import importlib.util

            # Parse and extract _warm_portfolio_cache source
            app_path = os.path.join(os.path.dirname(__file__), 'src', 'app.py')
            with open(app_path) as f:
                source = f.read()

            tree = ast.parse(source)
            func_src_lines = source.splitlines()

            # Find line numbers of _warm_portfolio_cache
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == '_warm_portfolio_cache':
                    start = node.lineno - 1
                    end = node.end_lineno
                    func_source = '\n'.join(func_src_lines[start:end])
                    break

            # Build minimal namespace with the mock
            ns = {
                'get_portfolio_service': lambda: mock_svc,
            }
            exec(func_source, ns)
            ns['_warm_portfolio_cache']('user-abc')

        mock_svc.list_portfolios.assert_called_once_with('user-abc')
        self.assertEqual(mock_svc.db.get_holdings.call_count, 2)
        mock_svc.db.get_holdings.assert_any_call('1')
        mock_svc.db.get_holdings.assert_any_call('2')

    def test_warm_portfolio_cache_swallows_all_exceptions(self):
        """_warm_portfolio_cache must not raise even when service throws."""
        mock_svc = MagicMock()
        mock_svc.list_portfolios.side_effect = RuntimeError("DB is down")

        with patch('portfolio.portfolio_service.get_portfolio_service', return_value=mock_svc):
            import ast
            app_path = os.path.join(os.path.dirname(__file__), 'src', 'app.py')
            with open(app_path) as f:
                source = f.read()
            tree = ast.parse(source)
            func_src_lines = source.splitlines()
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == '_warm_portfolio_cache':
                    start = node.lineno - 1
                    end = node.end_lineno
                    func_source = '\n'.join(func_src_lines[start:end])
                    break
            ns = {'get_portfolio_service': lambda: mock_svc}
            exec(func_source, ns)
            try:
                ns['_warm_portfolio_cache']('user-xyz')
            except Exception as e:
                self.fail(f"_warm_portfolio_cache raised an exception: {e}")

    def test_warm_portfolio_cache_thread_spawn_in_login_required(self):
        """login_required block must spawn a daemon thread targeting _warm_portfolio_cache."""
        import ast
        app_path = os.path.join(os.path.dirname(__file__), 'src', 'app.py')
        with open(app_path) as f:
            source = f.read()

        # Check that threading.Thread is called with _warm_portfolio_cache as target
        # and daemon=True, within the same block that sets session['user_id']
        self.assertIn('_warm_portfolio_cache', source,
                      "Threading spawn of _warm_portfolio_cache not found in app.py")
        self.assertIn('daemon=True', source,
                      "daemon=True not found in threading.Thread call in app.py")
        # Both must appear near the session assignment block
        idx_thread = source.find('threading.Thread(target=_warm_portfolio_cache')
        idx_session = source.find("session['user_id'] = clerk_user_id")
        self.assertNotEqual(idx_thread, -1,
                            "threading.Thread(target=_warm_portfolio_cache) not found")
        self.assertNotEqual(idx_session, -1,
                            "session['user_id'] = clerk_user_id not found")
        # Thread spawn should come AFTER session assignment (within ~300 chars)
        self.assertGreater(idx_thread, idx_session,
                           "Thread spawn should appear after session['user_id'] = clerk_user_id")
        self.assertLess(idx_thread - idx_session, 300,
                        "Thread spawn is too far from session assignment — may be in wrong place")


if __name__ == '__main__':
    unittest.main()
