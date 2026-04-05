"""
PlannerAgent as a LangGraph node.

Selects and prioritises research subjects based on ticker, trade type,
and conversation context. Single structured-JSON LLM call, no tools.
"""

import json
import logging
import os
import re
from typing import List

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from research_plan import ResearchPlan
from research_subjects import ResearchSubject, get_research_subjects_for_trade_type

logger = logging.getLogger(__name__)

PLANNER_MODEL = os.getenv("PLANNER_MODEL", "gemini-2.5-flash")
PLANNER_MAX_SUBJECTS = int(os.getenv("PLANNER_MAX_SUBJECTS", "8"))


def _build_system_prompt(
    ticker: str, trade_type: str, eligible: List[ResearchSubject], locked: bool = False
) -> str:
    subject_lines = "\n".join(
        f'  - "{s.id}": {s.name} — {s.description}' for s in eligible
    )
    if locked:
        subject_rule = (
            "Use exactly these subjects in this order. Do not add or remove any."
        )
    else:
        subject_rule = "Include ALL eligible subjects unless the user context makes one clearly irrelevant."
    return f"""You are a research planning assistant for a stock analysis platform.

Your job is to select the most relevant research subjects for a {trade_type} analysis of {ticker},
and to write per-subject focus hints that reflect what the user actually cares about.

**Available subjects for {trade_type}:**
{subject_lines}

**Output a JSON object with exactly these keys:**
{{
  "selected_subject_ids": ["id1", "id2", ...],
  "subject_focus": {{
    "subject_id": "one-sentence focus hint referencing user's specific concern",
    ...
  }},
  "trade_context": "2-3 sentence summary of user goals for the synthesis agent",
  "reasoning": "your internal reasoning (logged only, never shown to user)"
}}

Rules:
- {subject_rule}
- Order subjects by research importance for this specific situation.
- Focus hints should be specific to user concerns; leave as "" when no particular focus applies.
- trade_context is prose written for a synthesis agent, not bullet points.
- reasoning is for logging only — be candid about your choices."""


def _build_user_prompt(
    ticker: str,
    trade_type: str,
    conversation_context: str,
    eligible: List[ResearchSubject],
) -> str:
    context_section = (
        f"**User conversation context:**\n{conversation_context}"
        if conversation_context.strip()
        else "**User conversation context:** (none provided)"
    )
    eligible_ids = [s.id for s in eligible]
    return f"""Ticker: {ticker}
Trade Type: {trade_type}
Eligible subject IDs: {eligible_ids}

{context_section}

Build the research plan JSON now."""


def _parse_response(
    raw_json: str,
    ticker: str,
    trade_type: str,
    eligible: List[ResearchSubject],
) -> ResearchPlan:
    eligible_ids = {s.id for s in eligible}
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("JSON parse failed (%s); using fallback.", exc)
        return _fallback_plan(ticker, trade_type, eligible)

    raw_ids = data.get("selected_subject_ids", [])
    if not isinstance(raw_ids, list):
        raw_ids = []
    selected_ids = [sid for sid in raw_ids if sid in eligible_ids]
    present = set(selected_ids)
    for s in eligible:
        if s.id not in present:
            selected_ids.append(s.id)

    raw_focus = data.get("subject_focus", {})
    subject_focus = {}
    if isinstance(raw_focus, dict):
        for sid in selected_ids:
            hint = raw_focus.get(sid, "")
            subject_focus[sid] = hint if isinstance(hint, str) else ""

    trade_context = data.get("trade_context", "")
    if not isinstance(trade_context, str):
        trade_context = ""

    planner_reasoning = data.get("reasoning", "")
    if not isinstance(planner_reasoning, str):
        planner_reasoning = ""

    return ResearchPlan(
        ticker=ticker,
        trade_type=trade_type,
        selected_subject_ids=selected_ids,
        subject_focus=subject_focus,
        trade_context=trade_context,
        planner_reasoning=planner_reasoning,
    )


def _fallback_plan(
    ticker: str, trade_type: str, eligible: List[ResearchSubject]
) -> ResearchPlan:
    return ResearchPlan(
        ticker=ticker,
        trade_type=trade_type,
        selected_subject_ids=[s.id for s in eligible],
        subject_focus={s.id: "" for s in eligible},
        trade_context="",
        planner_reasoning="fallback: LLM call failed or returned invalid JSON",
    )


def planner_node(state: dict) -> dict:
    """
    LangGraph node: builds a ResearchPlan from state.

    Reads: ticker, trade_type, conversation_context, emitter
    Writes: plan
    """
    ticker = state["ticker"]
    trade_type = state["trade_type"]
    conversation_context = state.get("conversation_context", "")
    emitter = state.get("emitter")

    if emitter:
        emitter.emit("Building research plan...")

    eligible = get_research_subjects_for_trade_type(trade_type)
    eligible = eligible[:PLANNER_MAX_SUBJECTS]

    # Honour user's subject selection from popup
    user_selected = state.get("user_selected_subjects")
    if user_selected:
        selected_set = set(user_selected)
        eligible_filtered = [s for s in eligible if s.id in selected_set]
        # Restore user's ordering
        id_to_subject = {s.id: s for s in eligible_filtered}
        eligible = [id_to_subject[sid] for sid in user_selected if sid in id_to_subject]

    system_prompt = _build_system_prompt(
        ticker, trade_type, eligible, locked=bool(user_selected)
    )
    user_prompt = _build_user_prompt(ticker, trade_type, conversation_context, eligible)

    llm = ChatGoogleGenerativeAI(
        model=PLANNER_MODEL,
        temperature=0.3,
        max_output_tokens=2000,
    )

    input_tok = 0
    output_tok = 0
    try:
        response = llm.invoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
        )
        usage = getattr(response, "usage_metadata", None) or {}
        input_tok = usage.get("input_tokens", 0)
        output_tok = usage.get("output_tokens", 0)

        raw_json = response.content
        # Strip markdown code fences if present
        if "```" in raw_json:
            raw_json = raw_json.split("```")[1]
            if raw_json.startswith("json"):
                raw_json = raw_json[4:]
        plan = _parse_response(raw_json, ticker, trade_type, eligible)
    except Exception as exc:
        logger.warning("LLM call failed (%s); using fallback.", exc)
        plan = _fallback_plan(ticker, trade_type, eligible)

    # Deterministically extract the raw position block (no LLM needed)
    pos_match = re.search(
        r"(User's existing position:.+?)(?:\n\n|\Z)",
        conversation_context,
        re.DOTALL,
    )
    if pos_match:
        plan.position_summary = pos_match.group(1).strip()

    subject_names = ", ".join(plan.selected_subject_ids)
    logger.info(
        "Plan: %s subjects — %s, %s/%s tokens",
        len(plan.selected_subject_ids),
        subject_names,
        input_tok,
        output_tok,
    )
    if emitter:
        emitter.emit(f"Researching: {subject_names}...")
    if progress_fn := state.get("progress_fn"):
        n = len(plan.selected_subject_ids)
        progress_fn(15, f"Planning: {n} subjects selected")

    # Compute budget settings here so _fan_out can read them from state
    # (avoids InvalidUpdateError from parallel specialized_nodes all returning the same field)
    from spend_budget import (
        compute_effective_specialized_settings_from_plan,
    )
    import os as _os

    spend_budget_usd = state.get("spend_budget_usd")
    if spend_budget_usd is None:
        spend_budget_usd = float("inf")
    subject_ids = plan.selected_subject_ids[
        : int(_os.getenv("MAX_RESEARCH_SUBJECTS", "8"))
    ]
    try:
        budget = compute_effective_specialized_settings_from_plan(
            ticker=ticker,
            trade_type=trade_type,
            plan=plan,
            selected_subject_ids=subject_ids,
            spend_budget_usd=spend_budget_usd,
        )
    except Exception as exc:
        logger.warning("Budget computation failed (%s); using defaults.", exc)
        budget = {
            "effective_max_turns": int(_os.getenv("SPECIALIZED_AGENT_MAX_TURNS", "8")),
            "effective_max_output_tokens": int(
                _os.getenv("SPECIALIZED_AGENT_MAX_OUTPUT_TOKENS", "6000")
            ),
            "estimated_spend_usd": None,
            "budget_exhausted": False,
        }
    logger.debug("Budget: %s", budget)

    return {
        "plan": plan,
        "actual_input_tokens": input_tok,
        "actual_output_tokens": output_tok,
        "estimated_spend_usd": budget.get("estimated_spend_usd"),
        "effective_max_turns": budget.get("effective_max_turns"),
        "effective_max_output_tokens": budget.get("effective_max_output_tokens"),
        "effective_subject_count": budget.get("effective_subject_count"),
        "budget_exhausted": budget.get("budget_exhausted", False),
    }
