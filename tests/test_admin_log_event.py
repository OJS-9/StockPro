"""
admin_log_event() must refuse to write rows with no user_id (issue #145).

A null user_id produces analytics rows that corrupt any aggregate grouped or
filtered by user_id (e.g. the cohort return-rate watch). Several call sites can
hand admin_log_event a None (research_graph.storage_node when run_research gets
no user, the admin config routes via getattr(request, "admin_user_id", None)),
so the guard lives in the writer itself to cover all of them.
"""

from unittest.mock import MagicMock, patch

import pytest

from database import DatabaseManager


def _make_manager():
    mgr = DatabaseManager.__new__(DatabaseManager)
    mock_cur = MagicMock()
    mock_conn = MagicMock()
    ctx = MagicMock()
    ctx.__enter__.return_value = mock_cur
    ctx.__exit__.return_value = None
    mock_conn.cursor.return_value = ctx
    return mgr, mock_cur, mock_conn


def _run(mgr, mock_conn, user_id):
    with patch.object(mgr, "get_connection", return_value=mock_conn):
        with patch.object(mgr, "_release"):
            mgr.admin_log_event("research_complete", user_id, {"ticker": "AAPL"})


@pytest.mark.parametrize("user_id", [None, "", 0])
def test_null_user_id_writes_nothing(user_id):
    mgr, mock_cur, mock_conn = _make_manager()
    _run(mgr, mock_conn, user_id)

    mock_cur.execute.assert_not_called()
    mock_conn.commit.assert_not_called()


def test_real_user_id_writes_event():
    mgr, mock_cur, mock_conn = _make_manager()
    _run(mgr, mock_conn, "user-1")

    mock_cur.execute.assert_called_once()
    sql = mock_cur.execute.call_args[0][0]
    assert "INSERT INTO admin_events" in sql
    mock_conn.commit.assert_called_once()
