"""
LangSmith observability + SSE step emission.

LangSmith auto-traces all LangChain/LangGraph calls when these env vars are set:
    LANGSMITH_API_KEY=...
    LANGSMITH_PROJECT=stockintel
    LANGCHAIN_TRACING_V2=true

This module only provides the lightweight SSE step queue used to stream
progress messages to the UI during report generation.

When LANGCHAIN_TRACING_V2 and LANGSMITH_API_KEY are set, pass
`synthesis_invoke_config(...)` into ChatGoogleGenerativeAI.invoke(..., config=...)
so LangSmith runs include ticker / trade_type / node metadata.
"""

import queue
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class StepEmitter:
    """Lightweight SSE step queue. LangSmith handles all LLM/tool tracing automatically."""

    step_queue: Optional[queue.Queue] = field(default=None)

    def emit(self, msg: str):
        """Push a step message to the SSE queue (fire-and-forget)."""
        if self.step_queue is not None:
            try:
                self.step_queue.put_nowait({"type": "step", "message": msg})
            except Exception:
                pass


def create_emitter(step_queue: Optional[queue.Queue] = None) -> StepEmitter:
    """Create a StepEmitter for SSE progress streaming."""
    return StepEmitter(step_queue=step_queue)


def synthesis_invoke_config(ticker: str, trade_type: str) -> Dict[str, Any]:
    """RunnableConfig for synthesis LLM calls — tags/metadata for LangSmith dashboards."""
    return {
        "tags": ["synthesis", "stockpro"],
        "metadata": {
            "ticker": (ticker or "").strip().upper(),
            "trade_type": (trade_type or "").strip(),
            "stockpro_node": "synthesis",
        },
    }
