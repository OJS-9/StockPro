"""Round-trip tests for the generation_status / generation_events helpers
that back the multi-worker shared state in src/database.py.

These run against the real Postgres pointed at by DATABASE_URL (Supabase).
The new tables are namespaced and use TEST_ session_ids so they cannot
collide with real user data; each test cleans up after itself.
"""

import os
import time
import uuid

import pytest

from database import get_database_manager

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set",
)


@pytest.fixture
def db():
    return get_database_manager()


@pytest.fixture
def session_id():
    sid = f"TEST_GENSTATUS_{uuid.uuid4().hex[:12]}"
    yield sid
    # Cleanup
    conn = get_database_manager().get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM generation_events WHERE session_id = %s", (sid,))
            cur.execute("DELETE FROM generation_status WHERE session_id = %s", (sid,))
        conn.commit()
    finally:
        get_database_manager()._release(conn)


def test_set_and_get_round_trip(db, session_id):
    db.set_generation_status(
        session_id, "user_abc",
        status="in_progress", progress=42, step="Researching", step_code="researching",
    )
    row = db.get_generation_status(session_id)
    assert row is not None
    assert row["session_id"] == session_id
    assert row["user_id"] == "user_abc"
    assert row["status"] == "in_progress"
    assert row["progress"] == 42
    assert row["step"] == "Researching"


def test_get_missing_returns_none(db):
    assert db.get_generation_status("TEST_DOES_NOT_EXIST_XYZ") is None


def test_partial_update_does_not_clobber(db, session_id):
    db.set_generation_status(
        session_id, "user_abc",
        status="in_progress", progress=5, step="Starting", step_code="starting",
    )
    db.update_generation_status(session_id, progress=50, step="Halfway")
    row = db.get_generation_status(session_id)
    assert row["status"] == "in_progress"        # unchanged
    assert row["step_code"] == "starting"        # unchanged
    assert row["progress"] == 50                 # updated
    assert row["step"] == "Halfway"              # updated


def test_jsonb_questions_round_trip(db, session_id):
    questions = [{"id": "q1", "question": "Why?", "options": ["A", "B"]}]
    db.set_generation_status(
        session_id, "user_abc", status="needs_input", questions=questions,
    )
    row = db.get_generation_status(session_id)
    assert row["questions"] == questions


def test_upsert_preserves_owner_updates_other_fields(db, session_id):
    """Re-upserting with the same session_id keeps user_id (owner is sticky)
    but overwrites status/progress fields. This protects against accidental
    cross-user takeover of an in-flight session."""
    db.set_generation_status(session_id, "user_abc", status="in_progress")
    db.set_generation_status(session_id, "user_abc", status="ready", progress=100)
    row = db.get_generation_status(session_id)
    assert row["user_id"] == "user_abc"
    assert row["status"] == "ready"
    assert row["progress"] == 100


def test_unknown_field_rejected(db, session_id):
    with pytest.raises(ValueError):
        db.set_generation_status(session_id, "user_abc", bogus_field="x")


def test_append_event_returns_monotonic_seq(db, session_id):
    s1 = db.append_generation_event(session_id, "step", {"type": "step", "message": "a"})
    s2 = db.append_generation_event(session_id, "step", {"type": "step", "message": "b"})
    s3 = db.append_generation_event(session_id, "done", {"type": "done"})
    assert (s1, s2, s3) == (1, 2, 3)


def test_read_events_since(db, session_id):
    db.append_generation_event(session_id, "step", {"type": "step", "message": "a"})
    db.append_generation_event(session_id, "step", {"type": "step", "message": "b"})
    db.append_generation_event(session_id, "done", {"type": "done"})

    all_events = db.read_generation_events_since(session_id, 0)
    assert [e["seq"] for e in all_events] == [1, 2, 3]
    assert all_events[0]["payload"]["message"] == "a"
    assert all_events[2]["event_type"] == "done"

    only_after_1 = db.read_generation_events_since(session_id, 1)
    assert [e["seq"] for e in only_after_1] == [2, 3]


def test_evict_stale_drops_expired(db):
    sid = f"TEST_EVICT_{uuid.uuid4().hex[:12]}"
    # Insert with expires_at in the past via raw SQL to bypass DEFAULT.
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO generation_status (session_id, user_id, status, expires_at)
                   VALUES (%s, %s, %s, NOW() - INTERVAL '1 minute')""",
                (sid, "user_abc", "in_progress"),
            )
        conn.commit()
    finally:
        db._release(conn)
    db.append_generation_event(sid, "step", {"type": "step", "message": "stale"})

    db.evict_stale_generation_data()

    assert db.get_generation_status(sid) is None
    assert db.read_generation_events_since(sid, 0) == []
