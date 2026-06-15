"""
create_user() must be idempotent (issue #103).

The auth middleware calls create_user() whenever it sees no row for a user.
Parallel requests (multi-tab login) can both pass that check and both INSERT
the same user_id, so the INSERT must carry ON CONFLICT (user_id) DO NOTHING
or the losing request raises UniqueViolation and 500s every endpoint.
"""

from unittest.mock import MagicMock, patch

from database import DatabaseManager


def _make_manager(rowcount):
    mgr = DatabaseManager.__new__(DatabaseManager)
    mock_cur = MagicMock()
    mock_cur.rowcount = rowcount
    mock_conn = MagicMock()
    ctx = MagicMock()
    ctx.__enter__.return_value = mock_cur
    ctx.__exit__.return_value = None
    mock_conn.cursor.return_value = ctx
    return mgr, mock_cur, mock_conn


def _run_create_user(mgr, mock_conn):
    with patch.object(mgr, "get_connection", return_value=mock_conn):
        with patch.object(mgr, "_release"):
            with patch("database.encrypt", return_value="enc"):
                with patch("database.hmac_email", return_value="hash"):
                    mgr.admin_log_event = MagicMock()
                    mgr.create_user(
                        user_id="user-1", username="alice", email="a@b.com"
                    )
    return mgr.admin_log_event


def test_insert_uses_on_conflict_do_nothing():
    mgr, mock_cur, mock_conn = _make_manager(rowcount=1)
    _run_create_user(mgr, mock_conn)

    mock_cur.execute.assert_called_once()
    sql = mock_cur.execute.call_args[0][0]
    assert "ON CONFLICT (user_id) DO NOTHING" in sql


def test_signup_logged_on_first_insert():
    mgr, mock_cur, mock_conn = _make_manager(rowcount=1)
    log = _run_create_user(mgr, mock_conn)

    log.assert_called_once_with("signup", "user-1", {"username": "alice"})
    mock_conn.commit.assert_called_once()


def test_signup_not_logged_on_duplicate_insert():
    """rowcount 0 means the row already existed — no second signup event."""
    mgr, mock_cur, mock_conn = _make_manager(rowcount=0)
    log = _run_create_user(mgr, mock_conn)

    log.assert_not_called()
    mock_conn.commit.assert_called_once()
