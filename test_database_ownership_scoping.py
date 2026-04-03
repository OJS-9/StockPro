"""
DatabaseManager ownership scoping (complements app-layer checks and optional Supabase RLS).

Locks in SQL contracts so report reads used by authenticated routes stay user-scoped.
"""

from unittest.mock import MagicMock, patch

from database import DatabaseManager


def _cursor_context(mock_cur):
    ctx = MagicMock()
    ctx.__enter__.return_value = mock_cur
    ctx.__exit__.return_value = None
    return ctx


def test_get_report_with_user_id_uses_dual_key_query():
    mgr = DatabaseManager.__new__(DatabaseManager)
    mock_cur = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = _cursor_context(mock_cur)

    with patch.object(mgr, "get_connection", return_value=mock_conn):
        with patch.object(mgr, "_release"):
            mgr.get_report("rep-1", user_id="user-1")

    mock_cur.execute.assert_called_once()
    sql, params = mock_cur.execute.call_args[0]
    assert "AND user_id = %s" in sql
    assert params == ("rep-1", "user-1")


def test_get_report_without_user_id_uses_id_only_query():
    """Omitting user_id allows lookup by report_id alone — callers must pass user_id for auth reads."""
    mgr = DatabaseManager.__new__(DatabaseManager)
    mock_cur = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = _cursor_context(mock_cur)

    with patch.object(mgr, "get_connection", return_value=mock_conn):
        with patch.object(mgr, "_release"):
            mgr.get_report("rep-1", user_id=None)

    mock_cur.execute.assert_called_once()
    sql, params = mock_cur.execute.call_args[0]
    assert "AND user_id = %s" not in sql
    assert params == ("rep-1",)


def test_list_portfolios_with_user_id_filters_by_owner():
    mgr = DatabaseManager.__new__(DatabaseManager)
    mock_cur = MagicMock()
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = _cursor_context(mock_cur)

    with patch.object(mgr, "get_connection", return_value=mock_conn):
        with patch.object(mgr, "_release"):
            mgr.list_portfolios(user_id="user-99")

    mock_cur.execute.assert_called_once()
    sql, params = mock_cur.execute.call_args[0]
    assert "WHERE user_id = %s" in sql
    assert params == ("user-99",)
