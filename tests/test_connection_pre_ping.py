"""
get_connection() pre-ping: a pooled connection whose SSL layer was silently
dropped by Supabase reports conn.closed == 0 but fails on the first query.
get_connection() must detect that with a SELECT 1 ping, discard the dead
connection, and hand back a live one -- BUT only ping connections that have sat
idle long enough to plausibly be dead, so DB-heavy requests that reuse a warm
connection within the idle window pay no round-trip.
"""

import threading
import time

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
    conn._test_cursor = cur
    return conn


def _bare_manager():
    """A DatabaseManager with just the pre-ping bookkeeping wired up (no real pool)."""
    mgr = DatabaseManager.__new__(DatabaseManager)
    mgr._released_at = {}
    mgr._released_lock = threading.Lock()
    return mgr


def test_get_connection_skips_dead_socket_and_returns_live_one():
    dead = _make_conn(
        execute_side_effect=psycopg2.OperationalError(
            "SSL connection has been closed unexpectedly"
        )
    )
    healthy = _make_conn()

    fake_pool = MagicMock()
    fake_pool.getconn.side_effect = [dead, healthy]

    mgr = _bare_manager()
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

    mgr = _bare_manager()
    mgr._pool = fake_pool

    try:
        mgr.get_connection()
        assert False, "expected RuntimeError after retries"
    except RuntimeError as e:
        assert "live connection" in str(e)

    assert fake_pool.getconn.call_count == DatabaseManager._POOL_ACQUIRE_ATTEMPTS


def test_get_connection_skips_ping_for_recently_released_connection():
    """A connection returned to the pool moments ago is trusted without a SELECT 1.

    This is the regression guard: DB-heavy requests reuse warm connections many
    times, and pinging each one added a Supabase round-trip per checkout.
    """
    warm = _make_conn()

    fake_pool = MagicMock()
    fake_pool.getconn.return_value = warm

    mgr = _bare_manager()
    mgr._pool = fake_pool

    # Simulate the connection having just been released.
    mgr._release(warm)
    assert id(warm) in mgr._released_at

    conn = mgr.get_connection()

    assert conn is warm
    # No ping: the cursor/execute path was never touched on checkout.
    warm._test_cursor.execute.assert_not_called()
    # The release record is consumed on checkout so a stale id can't be reused.
    assert id(warm) not in mgr._released_at


def test_get_connection_pings_connection_idle_past_threshold():
    """A connection that sat idle beyond the threshold is still pinged."""
    stale = _make_conn()

    fake_pool = MagicMock()
    fake_pool.getconn.return_value = stale

    mgr = _bare_manager()
    mgr._pool = fake_pool

    # Mark it released far enough in the past to require a ping.
    mgr._released_at[id(stale)] = time.monotonic() - (
        DatabaseManager._PING_IF_IDLE_SECONDS + 5
    )

    conn = mgr.get_connection()

    assert conn is stale
    stale._test_cursor.execute.assert_called_once_with("SELECT 1")
    stale.rollback.assert_called_once()
