"""
_run_read / _run_write: a pooled connection silently dropped by Supabase
(SSL connection closed) surfaces as psycopg2.OperationalError mid-query. The
helpers must transparently retry on a fresh connection where it is provably
safe to do so, and must NOT retry genuine query errors or post-commit failures.

See issue #110.
"""

import threading

import psycopg2
from unittest.mock import MagicMock

from database import DatabaseManager


def _dropped_error():
    return psycopg2.OperationalError("SSL connection has been closed unexpectedly")


def _make_conn(closed=0):
    conn = MagicMock()
    conn.closed = closed
    return conn


def _bare_manager():
    """A DatabaseManager with just the retry bookkeeping wired up (no real pool)."""
    mgr = DatabaseManager.__new__(DatabaseManager)
    mgr._released_at = {}
    mgr._released_lock = threading.Lock()
    mgr._pool = MagicMock()
    return mgr


def _wire_connections(mgr, conns):
    """get_connection hands out the given connections in order; _release is a no-op
    we can assert on."""
    mgr.get_connection = MagicMock(side_effect=list(conns))
    mgr._release = MagicMock()
    return mgr


# ── reads ────────────────────────────────────────────────────────────────


def test_run_read_retries_on_dropped_connection():
    dead = _make_conn()
    healthy = _make_conn()
    mgr = _wire_connections(_bare_manager(), [dead, healthy])

    calls = []

    def op(conn):
        calls.append(conn)
        if conn is dead:
            # psycopg2 flips conn.closed after the failed execute.
            conn.closed = 1
            raise _dropped_error()
        return "rows"

    assert mgr._run_read(op) == "rows"
    assert calls == [dead, healthy]
    # The poisoned connection is discarded so the pool replaces it; the healthy
    # one is released normally, never force-closed.
    mgr._pool.putconn.assert_called_once_with(dead, close=True)
    mgr._release.assert_called_once_with(healthy)


def test_run_read_does_not_retry_real_query_error():
    """A statement timeout (QueryCanceled subclasses OperationalError) leaves the
    connection open -- it must surface, not retry, not force-close the conn."""
    conn = _make_conn()
    mgr = _wire_connections(_bare_manager(), [conn])

    timeout = psycopg2.errors.QueryCanceled(
        "canceling statement due to statement timeout"
    )

    def op(c):
        raise timeout

    try:
        mgr._run_read(op)
        assert False, "expected the query error to surface"
    except psycopg2.errors.QueryCanceled:
        pass

    assert mgr.get_connection.call_count == 1  # no retry
    mgr._pool.putconn.assert_not_called()  # conn not discarded
    mgr._release.assert_called_once_with(conn)  # released normally


def test_run_read_detects_drop_by_closed_flag_without_message_match():
    """Detection must not depend on the error wording: conn.closed != 0 alone
    proves the socket is gone."""
    dead = _make_conn()
    healthy = _make_conn()
    mgr = _wire_connections(_bare_manager(), [dead, healthy])

    def op(conn):
        if conn is dead:
            conn.closed = 1
            raise psycopg2.OperationalError("some unfamiliar libpq wording")
        return "ok"

    assert mgr._run_read(op) == "ok"
    mgr._pool.putconn.assert_called_once_with(dead, close=True)


def test_run_read_raises_when_every_connection_is_dead():
    """Mass-drop (Supabase kills all idle sockets): fail fast after one retry."""
    dead1 = _make_conn()
    dead2 = _make_conn()
    mgr = _wire_connections(_bare_manager(), [dead1, dead2])

    def op(conn):
        conn.closed = 1
        raise _dropped_error()

    try:
        mgr._run_read(op)
        assert False, "expected the dropped-connection error to surface"
    except psycopg2.OperationalError:
        pass

    assert mgr.get_connection.call_count == DatabaseManager._MAX_DB_TRIES
    assert mgr._pool.putconn.call_count == 2  # both discarded
    mgr._release.assert_not_called()  # nothing healthy to release


# ── writes ───────────────────────────────────────────────────────────────


def test_run_write_retries_pre_commit_drop_and_commits_on_retry():
    dead = _make_conn()
    healthy = _make_conn()
    mgr = _wire_connections(_bare_manager(), [dead, healthy])

    def op(conn):
        if conn is dead:
            conn.closed = 1
            raise _dropped_error()
        return "wrote"

    assert mgr._run_write(op) == "wrote"
    # Only the surviving connection is committed.
    healthy.commit.assert_called_once()
    dead.commit.assert_not_called()
    mgr._pool.putconn.assert_called_once_with(dead, close=True)


def test_run_write_does_not_retry_commit_failure():
    """If commit() itself drops, the server may already have committed -- retrying
    could double-apply the write, so it must NOT retry."""
    conn = _make_conn()
    mgr = _wire_connections(_bare_manager(), [conn])
    conn.commit.side_effect = _dropped_error()

    def op(c):
        return "wrote"

    try:
        mgr._run_write(op)
        assert False, "expected the commit failure to surface"
    except psycopg2.OperationalError:
        pass

    assert mgr.get_connection.call_count == 1  # no retry
    conn.commit.assert_called_once()
    mgr._release.assert_called_once_with(conn)


def test_run_write_does_not_retry_real_query_error():
    """A constraint violation must surface immediately, not retry."""
    conn = _make_conn()
    mgr = _wire_connections(_bare_manager(), [conn])

    def op(c):
        raise psycopg2.errors.UniqueViolation("duplicate key")

    try:
        mgr._run_write(op)
        assert False, "expected the integrity error to surface"
    except psycopg2.errors.UniqueViolation:
        pass

    assert mgr.get_connection.call_count == 1
    conn.commit.assert_not_called()
    mgr._pool.putconn.assert_not_called()
    mgr._release.assert_called_once_with(conn)
