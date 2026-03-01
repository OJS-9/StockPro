"""
PlannerAgent — selects and prioritises research subjects based on ticker,
trade type, and the user's conversation context.

Uses a single structured JSON call (no tool use) for speed and determinism.
"""

import json
import os
from typing import List, Optional

from google import genai
from google.genai import types
from dotenv import load_dotenv

from research_plan import ResearchPlan
from research_subjects import ResearchSubject, get_research_subjects_for_trade_type

load_dotenv()

PLANNER_MAX_SUBJECTS = int(os.getenv("PLANNER_MAX_SUBJECTS", "8"))
PLANNER_MODEL = os.getenv("PLANNER_MODEL", "gemini-3-flash-preview")


class PlannerAgent:
    """
    Builds a ResearchPlan from ticker, trade type, and conversation context.
    """

    def __init__(self, api_key: str = None):
        # api_key kept for interface compatibility; Gemini key comes from env
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            raise ValueError("GEMINI_API_KEY is required. Set it in your .env file.")
        self._client = genai.Client(api_key=gemini_key)

    def build_plan(
        self,
        ticker: str,
        trade_type: str,
        conversation_context: str,
        trace_context=None,
    ) -> ResearchPlan:
        """
        Build a ResearchPlan for the given ticker/trade type/context.
        Falls back to a safe default plan if the LLM call fails.
        """
        eligible = get_research_subjects_for_trade_type(trade_type)
        eligible = eligible[:PLANNER_MAX_SUBJECTS]

        system_prompt = self._build_system_prompt(ticker, trade_type, eligible)
        user_prompt = self._build_user_prompt(ticker, trade_type, conversation_context, eligible)

        span = trace_context.start_span("planner", input=ticker) if trace_context else None
        gen = None
        if trace_context:
            gen = trace_context.start_generation(
                name=f"llm:{PLANNER_MODEL}",
                model=PLANNER_MODEL,
                input={"system": system_prompt, "messages": [{"role": "user", "content": user_prompt}]},
                parent_span=span,
            )
        try:
            response = self._client.models.generate_content(
                model=PLANNER_MODEL,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.3,
                    max_output_tokens=1200,
                    response_mime_type="application/json",
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            raw_json = response.text
            if trace_context and gen:
                trace_context.end_generation(gen, output=raw_json, usage=getattr(response, "usage_metadata", None))
            plan = self._parse_response(raw_json, ticker, trade_type, eligible)
            if trace_context:
                trace_context.end_span(span, output=plan.selected_subject_ids)
            return plan

        except Exception as exc:
            print(f"[PlannerAgent] LLM call failed ({exc}); using full eligible subject list.")
            if trace_context and gen:
                trace_context.end_generation(gen)
            if trace_context:
                trace_context.end_span(span, error=str(exc))
            return self._fallback_plan(ticker, trade_type, eligible)

    def _build_system_prompt(self, ticker: str, trade_type: str, eligible: List[ResearchSubject]) -> str:
        subject_lines = "\n".join(
            f'  - "{s.id}": {s.name} — {s.description}' for s in eligible
        )
        return f"""You are a research planning assistant for a stock analysis platform.

Your job is to select the most relevant research subjects for a {trade_type} analysis of {ticker},
and to write per-subject focus hints that reflect what the user actually cares about.

**Available subjects for {trade_type}:**
{subject_lines}

**Output a JSON object with exactly these keys:**
{{
  "selected_subject_ids": ["id1", "id2", ...],  // ordered by importance
  "subject_focus": {{
    "subject_id": "one-sentence focus hint referencing user's specific concern",
    ...
  }},
  "trade_context": "2-3 sentence summary of user goals for the synthesis agent",
  "reasoning": "your internal reasoning (logged only, never shown to user)"
}}

Rules:
- Include ALL eligible subjects unless the user context makes one clearly irrelevant.
- Order subjects by research importance for this specific situation.
- Focus hints should be specific to user concerns; leave as "" when no particular focus applies.
- trade_context is prose written for a synthesis agent, not bullet points.
- reasoning is for logging only — be candid about your choices."""

    def _build_user_prompt(
        self,
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
        self,
        raw_json: str,
        ticker: str,
        trade_type: str,
        eligible: List[ResearchSubject],
    ) -> ResearchPlan:
        eligible_ids = {s.id for s in eligible}

        try:
            data = json.loads(raw_json)
        except (json.JSONDecodeError, TypeError) as exc:
            print(f"[PlannerAgent] JSON parse failed ({exc}); using fallback.")
            return self._fallback_plan(ticker, trade_type, eligible)

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

    def _fallback_plan(self, ticker: str, trade_type: str, eligible: List[ResearchSubject]) -> ResearchPlan:
        return ResearchPlan(
            ticker=ticker,
            trade_type=trade_type,
            selected_subject_ids=[s.id for s in eligible],
            subject_focus={s.id: "" for s in eligible},
            trade_context="",
            planner_reasoning="fallback: LLM call failed or returned invalid JSON",
        )
