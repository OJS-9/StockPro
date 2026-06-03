"""
get_connection() pre-ping: a pooled connection whose SSL layer was silently
dropped by Supabase reports conn.closed == 0 but fails on the first query.
get_connection() must detect that with a SELECT 1 ping, discard the dead
connection, and hand back a live one.
"""

import psycopg2
from unittest.mock import MagicMock

from database import DatabaseManager


def _cursor_context(mock_cur):
    ctx = MagicMock()
    ctx.__enter__.return_value = mock_cur
    ctx.__exit__.return_value = None
    return ctx


def _make_conn(execute_side_effect=None):
    conn = MagicMock()
    conn.closed = 0
    cur = MagicMock()
    if execute_side_effect is not None:
        cur.execute.side_effect = execute_side_effect
    conn.cursor.return_value = _cursor_context(cur)
    return conn


def test_get_connection_skips_dead_socket_and_returns_live_one():
    dead = _make_conn(
        execute_side_effect=psycopg2.OperationalError(
            "SSL connection has been closed unexpectedly"
        )
    )
    healthy = _make_conn()

    fake_pool = MagicMock()
    fake_pool.getconn.side_effect = [dead, healthy]

    mgr = DatabaseManager.__new__(DatabaseManager)
    mgr._pool = fake_pool

    conn = mgr.get_connection()

    assert conn is healthy
    # The dead connection is discarded with close=True so its slot is freed.
    fake_pool.putconn.assert_called_once_with(dead, close=True)
    # The healthy connection was pinged then rolled back, never closed.
    healthy.rollback.assert_called_once()


def test_get_connection_raises_after_exhausting_retries():
    dead = _make_conn(
        execute_side_effect=psycopg2.OperationalError("still dead")
    )

    fake_pool = MagicMock()
    fake_pool.getconn.return_value = dead

    mgr = DatabaseManager.__new__(DatabaseManager)
    mgr._pool = fake_pool

    try:
        mgr.get_connection()
        assert False, "expected RuntimeError after retries"
    except RuntimeError as e:
        assert "live connection" in str(e)

    assert fake_pool.getconn.call_count == DatabaseManager._POOL_ACQUIRE_ATTEMPTS
