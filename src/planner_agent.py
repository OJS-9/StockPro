"""
PlannerAgent — selects and prioritises research subjects based on ticker,
trade type, and the user's conversation context.

Uses a single structured JSON call (no tool use) for speed and determinism.
"""

import json
import os
from typing import List

from openai import OpenAI

from research_plan import ResearchPlan
from research_subjects import ResearchSubject, get_research_subjects_for_trade_type

# Maximum subjects passed to the planner (caps the menu shown to the LLM).
# Individual trade-type catalogs are small enough that this rarely fires,
# but it prevents runaway costs if the catalog grows.
PLANNER_MAX_SUBJECTS = int(os.getenv("PLANNER_MAX_SUBJECTS", "8"))


class PlannerAgent:
    """
    Builds a ResearchPlan from ticker, trade type, and conversation context.

    The plan specifies:
    - which research subjects to run (ordered by priority)
    - per-subject focus hints derived from the user's stated goals
    - a distilled trade_context for the synthesis agent
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OpenAI API key is required. Set OPENAI_API_KEY environment variable."
            )
        self._client = OpenAI(api_key=self.api_key)

    # ─── Public API ──────────────────────────────────────────────────────────

    def build_plan(
        self,
        ticker: str,
        trade_type: str,
        conversation_context: str,
    ) -> ResearchPlan:
        """
        Build a ResearchPlan for the given ticker/trade type/context.

        Falls back to a safe default plan if the LLM call fails or returns
        unparseable JSON.

        Args:
            ticker: Stock ticker symbol.
            trade_type: One of "Day Trade", "Swing Trade", "Investment".
            conversation_context: Raw user messages from the Q&A phase.

        Returns:
            ResearchPlan ready for the orchestrator.
        """
        eligible = get_research_subjects_for_trade_type(trade_type)
        # Cap the catalog shown to the planner
        eligible = eligible[:PLANNER_MAX_SUBJECTS]

        system_prompt = self._build_system_prompt(ticker, trade_type, eligible)
        user_prompt = self._build_user_prompt(
            ticker, trade_type, conversation_context, eligible
        )

        try:
            response = self._client.chat.completions.create(
                model="gpt-4o",
                temperature=0.3,
                max_tokens=1200,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            raw_json = response.choices[0].message.content
            return self._parse_response(raw_json, ticker, trade_type, eligible)

        except Exception as exc:
            print(
                f"[PlannerAgent] LLM call failed ({exc}); using full eligible subject list."
            )
            return self._fallback_plan(ticker, trade_type, eligible)

    # ─── Prompt Builders ─────────────────────────────────────────────────────

    def _build_system_prompt(
        self,
        ticker: str,
        trade_type: str,
        eligible: List[ResearchSubject],
    ) -> str:
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

    # ─── Response Parser ─────────────────────────────────────────────────────

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

        # Validate and filter selected_subject_ids
        raw_ids = data.get("selected_subject_ids", [])
        if not isinstance(raw_ids, list):
            raw_ids = []
        # Keep only valid IDs, preserve order
        selected_ids = [sid for sid in raw_ids if sid in eligible_ids]
        # Append any eligible subject that was omitted (safety net)
        present = set(selected_ids)
        for s in eligible:
            if s.id not in present:
                selected_ids.append(s.id)

        # Parse focus hints — default to "" for missing/invalid entries
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

    # ─── Fallback ────────────────────────────────────────────────────────────

    def _fallback_plan(
        self,
        ticker: str,
        trade_type: str,
        eligible: List[ResearchSubject],
    ) -> ResearchPlan:
        """Return a safe plan using all eligible subjects and empty focus hints."""
        return ResearchPlan(
            ticker=ticker,
            trade_type=trade_type,
            selected_subject_ids=[s.id for s in eligible],
            subject_focus={s.id: "" for s in eligible},
            trade_context="",
            planner_reasoning="fallback: LLM call failed or returned invalid JSON",
        )
