"""
LangGraph StateGraph for the full research pipeline.

Flow:
  START → planner_node → fan_out → [specialized_node × N in parallel] → synthesis_node → storage_node → END

Parallel fan-out is implemented via the Send() API so each research subject
runs as a separate, concurrent node invocation.
"""

import operator
import os
import re
import uuid
import math
from typing import TypedDict, Dict, Any, Annotated, Optional, List

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from langgraph.checkpoint.memory import MemorySaver

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
    failed_subjects: List[str]                             # subject_ids that errored (set by quality_gate_node)
    is_partial_report: bool                                # True if some subjects failed
    report_text: str                                       # set by synthesis_node
    report_id: str                                         # set by storage_node
    user_id: Optional[int]
    emitter: Optional[StepEmitter]
    user_selected_subjects: Optional[List[str]]            # set from popup subject selection
    spend_budget_usd: Optional[float]                      # estimated USD budget for this run
    estimated_spend_usd: Optional[float]                  # estimated from prompt-size heuristics
    effective_max_turns: Optional[int]                    # per-subject cap used by specialized_node
    effective_max_output_tokens: Optional[int]            # per-subject cap used by specialized_node
    effective_subject_count: Optional[int]                # subject count after budget trimming
    budget_exhausted: bool                                 # True when min caps still exceed budget
    actual_input_tokens: Annotated[int, operator.add]     # summed across all nodes
    actual_output_tokens: Annotated[int, operator.add]    # summed across all nodes
    actual_cost_usd: Optional[float]                      # computed in storage_node


_MAX_SUBJECTS = int(os.getenv("MAX_RESEARCH_SUBJECTS", "8"))
_MIN_OUTPUT_CHARS = int(os.getenv("QUALITY_GATE_MIN_OUTPUT_CHARS", "200"))
_URL_RE = re.compile(r"https?://[^\s<>\"{}|\\^`\[\]]+")


def _fan_out(state: ResearchState) -> List[Send]:
    """Route one specialized_node per subject in the plan (parallel fan-out)."""
    plan = state["plan"]
    subject_ids = plan.selected_subject_ids[:_MAX_SUBJECTS]

    # Apply budget-driven subject cap (trims lowest-priority subjects first,
    # since the planner orders them by priority).
    effective_subject_count = state.get("effective_subject_count")
    if effective_subject_count is not None and effective_subject_count < len(subject_ids):
        trimmed = subject_ids[:effective_subject_count]
        dropped = subject_ids[effective_subject_count:]
        print(f"[FanOut] Budget trimmed subjects from {len(subject_ids)} → {effective_subject_count}. Dropped: {dropped}")
        subject_ids = trimmed

    return [
        Send("specialized_node", {**state, "subject_id": sid})
        for sid in subject_ids
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
    is_partial_report = state.get("is_partial_report", False)
    spend_budget_usd = state.get("spend_budget_usd")
    estimated_spend_usd = state.get("estimated_spend_usd")
    effective_max_turns = state.get("effective_max_turns")
    effective_max_output_tokens = state.get("effective_max_output_tokens")
    effective_subject_count = state.get("effective_subject_count")
    budget_exhausted = state.get("budget_exhausted", False)

    # MySQL JSON column rejects non-standard JSON floats like Infinity/NaN.
    def _sanitize_json_float(val: Optional[float]) -> Optional[float]:
        if val is None:
            return None
        try:
            # math.isfinite(None) raises, hence guard above.
            if isinstance(val, (int, float)) and not math.isfinite(float(val)):
                return None
        except Exception:
            return None
        return val

    spend_budget_usd = _sanitize_json_float(spend_budget_usd)
    estimated_spend_usd = _sanitize_json_float(estimated_spend_usd)

    actual_input_tokens = state.get("actual_input_tokens", 0)
    actual_output_tokens = state.get("actual_output_tokens", 0)
    actual_cost_usd = None
    try:
        from spend_budget import get_gemini_usd_rates
        rates = get_gemini_usd_rates()
        if rates and (actual_input_tokens or actual_output_tokens):
            actual_cost_usd = (
                (actual_input_tokens / 1000) * rates["input_rate"] +
                (actual_output_tokens / 1000) * rates["output_rate"]
            )
    except Exception as exc:
        print(f"[StorageNode] Could not compute actual cost: {exc}")
    actual_cost_usd = _sanitize_json_float(actual_cost_usd)

    if emitter:
        emitter.emit("Storing report...")

    report_id = str(uuid.uuid4())

    metadata = {
        "trade_type": trade_type,
        "research_subjects": plan.selected_subject_ids,
        "trade_context": plan.trade_context,
        "planner_reasoning": plan.planner_reasoning,
        "completeness": "partial" if is_partial_report else "complete",
        "failed_subjects": state.get("failed_subjects", []),
        "spend_budget_usd": spend_budget_usd,
        "estimated_spend_usd": estimated_spend_usd,
        "effective_max_turns": effective_max_turns,
        "effective_max_output_tokens": effective_max_output_tokens,
        "effective_subject_count": effective_subject_count,
        "budget_exhausted": budget_exhausted,
        "actual_input_tokens": actual_input_tokens,
        "actual_output_tokens": actual_output_tokens,
        "actual_cost_usd": actual_cost_usd,
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

        research_outputs = state.get("research_outputs", {})
        if research_outputs:
            storage.store_research_chunks(report_id, research_outputs)
    except Exception as e:
        print(f"[StorageNode] Storage failed (report still available): {e}")

    return {"report_id": report_id}


def quality_gate_node(state: ResearchState) -> dict:
    """
    Filter errored specialized_node outputs before synthesis.

    Separates failed subjects (those with an 'error' key in their result),
    aborts with an error report_text if >50% of subjects failed, otherwise
    passes cleaned outputs and a failed_subjects list to synthesis.
    """
    research_outputs = state["research_outputs"]
    emitter = state.get("emitter")
    ticker = state["ticker"]

    failed = []
    clean_outputs = {}
    for sid, result in research_outputs.items():
        if result.get("error"):
            failed.append(sid)
        elif len(result.get("research_output", "")) < _MIN_OUTPUT_CHARS:
            char_count = len(result.get("research_output", ""))
            print(f"[QualityGate] {sid}: output too short ({char_count} chars) — treating as failure")
            failed.append(sid)
        else:
            urls = list(dict.fromkeys(_URL_RE.findall(result.get("research_output", ""))))
            clean_outputs[sid] = {**result, "sources": urls}

    total = len(research_outputs)
    failed_count = len(failed)

    if emitter and failed_count:
        emitter.emit(f"Warning: {failed_count}/{total} research subjects failed")

    if total > 0 and failed_count / total > 0.5:
        error_text = (
            f"Research generation failed for {ticker}: "
            f"{failed_count} of {total} subjects returned errors "
            f"({', '.join(failed)}). Please try again."
        )
        print(f"[QualityGate] Aborting synthesis — too many failures: {failed}")
        return {
            "research_outputs": clean_outputs,
            "failed_subjects": failed,
            "is_partial_report": True,
            "report_text": error_text,
        }

    if failed_count:
        print(f"[QualityGate] Proceeding with partial results. Failed: {failed}")

    return {
        "research_outputs": clean_outputs,
        "failed_subjects": failed,
        "is_partial_report": failed_count > 0,
    }


def _quality_gate_route(state: ResearchState) -> str:
    """Skip synthesis and go straight to storage if the gate already wrote an error report."""
    if state.get("is_partial_report") and state.get("report_text") and not state["research_outputs"]:
        return "storage_node"
    return "synthesis_node"


# Build the graph
_builder = StateGraph(ResearchState)
_builder.add_node("planner_node", planner_node)
_builder.add_node("specialized_node", specialized_node)
_builder.add_node("quality_gate_node", quality_gate_node)
_builder.add_node("synthesis_node", synthesis_node)
_builder.add_node("storage_node", storage_node)

_builder.add_edge(START, "planner_node")
_builder.add_conditional_edges("planner_node", _fan_out, ["specialized_node"])
_builder.add_edge("specialized_node", "quality_gate_node")
_builder.add_conditional_edges("quality_gate_node", _quality_gate_route, ["synthesis_node", "storage_node"])
_builder.add_edge("synthesis_node", "storage_node")
_builder.add_edge("storage_node", END)

_checkpointer = MemorySaver()
research_graph = _builder.compile(checkpointer=_checkpointer)


def run_research(
    ticker: str,
    trade_type: str,
    conversation_context: str = "",
    user_id: Optional[int] = None,
    emitter: Optional[StepEmitter] = None,
    selected_subjects: Optional[List[str]] = None,
    spend_budget_usd: Optional[float] = None,
    parent_config: Optional[Dict[str, Any]] = None,
    username: Optional[str] = None,
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
        "failed_subjects": [],
        "is_partial_report": False,
        "report_text": "",
        "report_id": "",
        "user_id": user_id,
        "emitter": emitter,
        "user_selected_subjects": selected_subjects,
        "spend_budget_usd": spend_budget_usd,
        "estimated_spend_usd": None,
        "effective_max_turns": None,
        "effective_max_output_tokens": None,
        "effective_subject_count": None,
        "budget_exhausted": False,
        "actual_input_tokens": 0,
        "actual_output_tokens": 0,
        "actual_cost_usd": None,
    }

    from langchain_core.runnables.config import merge_configs

    run_name = f"{username} - {ticker.upper()} Research" if username else f"{ticker.upper()} Research"
    invoke_config = merge_configs(
        parent_config or {},
        {"run_name": run_name, "configurable": {"thread_id": str(uuid.uuid4())}},
    )

    result = research_graph.invoke(initial_state, config=invoke_config)
    return result
