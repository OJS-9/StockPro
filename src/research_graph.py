"""
LangGraph StateGraph for the full research pipeline.

Flow:
  START → planner_node → fan_out → [specialized_node × N in parallel] → synthesis_node → storage_node → END

Parallel fan-out is implemented via the Send() API so each research subject
runs as a separate, concurrent node invocation.
"""

import operator
import os
import uuid
from typing import TypedDict, Dict, Any, Annotated, Optional, List

from langgraph.graph import StateGraph, START, END
from langgraph.constants import Send

from agents.planner_node import planner_node
from agents.specialized_node import specialized_node
from agents.synthesis_node import synthesis_node
from langsmith_service import StepEmitter


class ResearchState(TypedDict):
    ticker: str
    trade_type: str
    conversation_context: str
    plan: Any                                              # ResearchPlan (set by planner_node)
    subject_id: str                                        # set per Send() invocation
    research_outputs: Annotated[Dict[str, Any], operator.or_]  # merged across parallel nodes
    report_text: str                                       # set by synthesis_node
    report_id: str                                         # set by storage_node
    user_id: Optional[int]
    emitter: Optional[StepEmitter]


def _fan_out(state: ResearchState) -> List[Send]:
    """Route one specialized_node per subject in the plan (parallel fan-out)."""
    plan = state["plan"]
    return [
        Send("specialized_node", {**state, "subject_id": sid})
        for sid in plan.selected_subject_ids
    ]


def storage_node(state: ResearchState) -> dict:
    """Store the synthesized report with chunking and embeddings."""
    from report_storage import ReportStorage

    ticker = state["ticker"]
    trade_type = state["trade_type"]
    report_text = state["report_text"]
    plan = state["plan"]
    user_id = state.get("user_id")
    emitter = state.get("emitter")

    if emitter:
        emitter.emit("Storing report...")

    report_id = str(uuid.uuid4())

    metadata = {
        "trade_type": trade_type,
        "research_subjects": plan.selected_subject_ids,
        "trade_context": plan.trade_context,
        "planner_reasoning": plan.planner_reasoning,
    }

    try:
        storage = ReportStorage()
        report_id = storage.store_report(
            ticker=ticker,
            trade_type=trade_type,
            report_text=report_text,
            metadata=metadata,
            user_id=user_id,
        )
        print(f"[StorageNode] Report stored: {report_id}")
    except Exception as e:
        print(f"[StorageNode] Storage failed (report still available): {e}")

    return {"report_id": report_id}


# Build the graph
_builder = StateGraph(ResearchState)
_builder.add_node("planner_node", planner_node)
_builder.add_node("specialized_node", specialized_node)
_builder.add_node("synthesis_node", synthesis_node)
_builder.add_node("storage_node", storage_node)

_builder.add_edge(START, "planner_node")
_builder.add_conditional_edges("planner_node", _fan_out, ["specialized_node"])
_builder.add_edge("specialized_node", "synthesis_node")
_builder.add_edge("synthesis_node", "storage_node")
_builder.add_edge("storage_node", END)

research_graph = _builder.compile()


def run_research(
    ticker: str,
    trade_type: str,
    conversation_context: str = "",
    user_id: Optional[int] = None,
    emitter: Optional[StepEmitter] = None,
) -> Dict[str, Any]:
    """
    Execute the full research pipeline.

    Returns:
        dict with keys: ticker, trade_type, plan, research_outputs,
                        report_text, report_id
    """
    initial_state: ResearchState = {
        "ticker": ticker.upper(),
        "trade_type": trade_type,
        "conversation_context": conversation_context,
        "plan": None,
        "subject_id": "",
        "research_outputs": {},
        "report_text": "",
        "report_id": "",
        "user_id": user_id,
        "emitter": emitter,
    }

    result = research_graph.invoke(initial_state)
    return result
