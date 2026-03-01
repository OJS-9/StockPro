"""
Tracing service for LangFuse observability + SSE step emission.

LangFuse is optional — if LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are absent,
all tracing calls are no-ops. SSE steps still work regardless.

Uses LangFuse SDK v3 API: root = lf.start_span(...), children = root.start_span(...).
"""

import os
import queue
from dataclasses import dataclass, field
from typing import Optional, Any


def _get_langfuse():
    """Return a Langfuse client or None if keys are not configured."""
    # Re-read .env so a long-running server picks up keys added after startup
    try:
        from dotenv import load_dotenv
        load_dotenv(override=False)
    except Exception:
        pass

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

    print(f"[TRACE DEBUG] _get_langfuse: public_key={'SET' if public_key else 'MISSING'}, secret_key={'SET' if secret_key else 'MISSING'}")

    if not public_key or not secret_key:
        return None

    try:
        from langfuse import Langfuse
        lf = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
        print(f"[TRACE DEBUG] Langfuse client created OK")
        return lf
    except Exception as e:
        print(f"[TRACE DEBUG] Langfuse init failed: {e}")
        return None


@dataclass
class TraceContext:
    """Holds the root LangFuse span + a queue for SSE steps."""
    step_queue: Optional[queue.Queue] = field(default=None)
    _root_span: Any = field(default=None, repr=False)  # LangfuseSpan or None
    _lf: Any = field(default=None, repr=False)         # Langfuse client or None

    def emit_step(self, msg: str):
        """Push a step message to the SSE queue (fire-and-forget)."""
        if self.step_queue is not None:
            try:
                self.step_queue.put_nowait({"type": "step", "message": msg})
            except Exception:
                pass

    def start_span(self, name: str, input: Any = None):
        """Start a child LangFuse span. Returns span object or None."""
        if self._root_span is None:
            return None
        try:
            return self._root_span.start_span(name=name, input=input)
        except Exception:
            return None

    def end_span(self, span, output: Any = None, error: str = None):
        """End a LangFuse span."""
        if span is None:
            return
        try:
            if error:
                span.update(level="ERROR", status_message=error)
            if output is not None:
                span.update(output=output)
            span.end()
        except Exception:
            pass

    def start_generation(self, name: str, model: str, input: Any = None, parent_span: Any = None) -> Any:
        """Start a LangFuse generation span (for LLM calls). Returns generation or None."""
        parent = parent_span if parent_span is not None else self._root_span
        if parent is None:
            return None
        try:
            return parent.start_generation(name=name, model=model, input=input)
        except Exception:
            return None

    def end_generation(self, gen: Any, output: Any = None, usage: Any = None):
        """End a LangFuse generation span."""
        if gen is None:
            return
        try:
            update_kwargs: dict = {}
            if output is not None:
                update_kwargs["output"] = output
            if usage is not None:
                update_kwargs["usage"] = {
                    "input": getattr(usage, "prompt_token_count", None),
                    "output": getattr(usage, "candidates_token_count", None),
                    "total": getattr(usage, "total_token_count", None),
                }
            if update_kwargs:
                gen.update(**update_kwargs)
            gen.end()
        except Exception:
            pass

    def finish(self, output: Any = None):
        """End the root span and flush."""
        try:
            if self._root_span is not None:
                if output is not None:
                    self._root_span.update(output=output)
                self._root_span.end()
            if self._lf is not None:
                self._lf.flush()
        except Exception:
            pass


def create_trace(
    ticker: str,
    trade_type: str,
    session_id: str,
    step_queue: Optional[queue.Queue] = None,
) -> TraceContext:
    """Create a TraceContext for a research request."""
    lf = _get_langfuse()
    root_span = None
    if lf is not None:
        try:
            root_span = lf.start_span(
                name=f"research:{ticker}:{trade_type}",
                input={"ticker": ticker, "trade_type": trade_type, "session_id": session_id},
            )
        except Exception:
            pass
    return TraceContext(step_queue=step_queue, _root_span=root_span, _lf=lf)


def create_chat_trace(
    report_id: str,
    question: str,
    step_queue: Optional[queue.Queue] = None,
) -> TraceContext:
    """Create a TraceContext for a chat Q&A request."""
    lf = _get_langfuse()
    root_span = None
    if lf is not None:
        try:
            root_span = lf.start_span(
                name=f"chat:{report_id[:8]}",
                input=question,
            )
        except Exception:
            pass
    return TraceContext(step_queue=step_queue, _root_span=root_span, _lf=lf)
