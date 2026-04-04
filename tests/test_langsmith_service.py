"""Tests for SSE StepEmitter (LangSmith module surface)."""

import queue
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from langsmith_service import StepEmitter, create_emitter, synthesis_invoke_config


def test_create_emitter_defaults_to_no_queue():
    em = create_emitter()
    assert isinstance(em, StepEmitter)
    assert em.step_queue is None


def test_emit_no_queue_is_noop():
    em = StepEmitter(step_queue=None)
    em.emit("hello")  # should not raise


def test_emit_enqueues_step_message():
    q: queue.Queue = queue.Queue()
    em = create_emitter(q)
    em.emit("Planning research…")
    item = q.get_nowait()
    assert item == {"type": "step", "message": "Planning research…"}


def test_emit_swallows_full_queue():
    """Queue full / put failure must not break the research pipeline."""

    class BadQueue:
        def put_nowait(self, _item):
            raise queue.Full

    em = StepEmitter(step_queue=BadQueue())
    em.emit("x")  # must not raise


def test_synthesis_invoke_config_metadata():
    cfg = synthesis_invoke_config("aapl", "Investment")
    assert "synthesis" in cfg["tags"]
    assert cfg["metadata"]["ticker"] == "AAPL"
    assert cfg["metadata"]["trade_type"] == "Investment"
    assert cfg["metadata"]["stockpro_node"] == "synthesis"


def test_emit_swallows_generic_put_error():
    class ExplodingQueue:
        def put_nowait(self, _item):
            raise RuntimeError("boom")

    em = StepEmitter(step_queue=ExplodingQueue())
    em.emit("x")  # must not raise
