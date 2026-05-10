"""Integration test for the Postgres-backed SSE event queue.

This wires the real production pieces together:
    StepEmitter --put_nowait--> _PgEventQueue --DB INSERT--> generation_events
    consumer    <--SELECT seq>last_seq-- DatabaseManager.read_generation_events_since

If any of those break (the shim wiring, the DB schema, the JSONB serialization,
or the monotonic seq generation), this test fails.

It does NOT exercise the Flask /continue or /stream/<id> HTTP routes — those
require auth and are easier to verify via agent-browser. This test isolates
the cross-worker producer/consumer mechanism.
"""

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set",
)


@pytest.fixture
def session_id():
    sid = f"TEST_SSE_SHIM_{uuid.uuid4().hex[:12]}"
    yield sid
    # Cleanup
    from database import get_database_manager
    db = get_database_manager()
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM generation_events WHERE session_id = %s", (sid,))
            cur.execute("DELETE FROM generation_status WHERE session_id = %s", (sid,))
        conn.commit()
    finally:
        db._release(conn)


def test_emitter_through_shim_to_db(session_id):
    """StepEmitter.emit() should land as a row that the consumer can read."""
    from app import _PgEventQueue
    from langsmith_service import create_emitter
    from database import get_database_manager

    queue = _PgEventQueue(session_id)
    emitter = create_emitter(queue)

    # Producer side: simulate the agent emitting progress steps
    emitter.emit("Planning research subjects...")
    emitter.emit("Fetching financials")
    emitter.emit("Synthesizing report")

    # Consumer side: read what was written
    db = get_database_manager()
    events = db.read_generation_events_since(session_id, 0)

    assert [e["seq"] for e in events] == [1, 2, 3]
    assert all(e["event_type"] == "step" for e in events)
    assert events[0]["payload"]["message"] == "Planning research subjects..."
    assert events[2]["payload"]["message"] == "Synthesizing report"


def test_shim_handles_done_and_error_payloads(session_id):
    """The /continue producer puts dicts shaped like {type: 'done', ...}
    and {type: 'error', message: ...} directly. The shim must store both
    so the SSE consumer can yield them and break the loop on terminal types."""
    from app import _PgEventQueue
    from database import get_database_manager

    queue = _PgEventQueue(session_id)

    queue.put_nowait({"type": "step", "message": "starting"})
    queue.put({"type": "done", "assistant_message": "the answer", "sources": []})
    # An error payload would terminate the loop; verify it stores cleanly
    other_sid = session_id + "_err"
    err_queue = _PgEventQueue(other_sid)
    err_queue.put_nowait({"type": "error", "message": "boom"})

    db = get_database_manager()
    events = db.read_generation_events_since(session_id, 0)
    assert [e["event_type"] for e in events] == ["step", "done"]
    assert events[1]["payload"]["assistant_message"] == "the answer"

    err_events = db.read_generation_events_since(other_sid, 0)
    assert err_events[0]["event_type"] == "error"
    assert err_events[0]["payload"]["message"] == "boom"

    # Cleanup the extra session
    conn = db.get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM generation_events WHERE session_id = %s", (other_sid,))
        conn.commit()
    finally:
        db._release(conn)


def test_consumer_reads_only_new_events(session_id):
    """Simulating the /stream/<id> polling loop: each iteration reads only
    events with seq > last_seq, so we never re-emit the same SSE message."""
    from app import _PgEventQueue
    from database import get_database_manager

    queue = _PgEventQueue(session_id)
    db = get_database_manager()

    queue.put_nowait({"type": "step", "message": "a"})
    queue.put_nowait({"type": "step", "message": "b"})

    first_batch = db.read_generation_events_since(session_id, 0)
    assert [e["payload"]["message"] for e in first_batch] == ["a", "b"]
    last_seq = first_batch[-1]["seq"]

    # Consumer keeps polling — no new events yet
    assert db.read_generation_events_since(session_id, last_seq) == []

    # Producer emits more
    queue.put_nowait({"type": "step", "message": "c"})
    queue.put_nowait({"type": "done"})

    next_batch = db.read_generation_events_since(session_id, last_seq)
    assert [e["payload"].get("message") for e in next_batch] == ["c", None]
    assert next_batch[-1]["event_type"] == "done"
