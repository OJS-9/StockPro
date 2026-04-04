"""
ResearchPlan dataclass — output of PlannerAgent, input to ResearchOrchestrator and SynthesisAgent.
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ResearchPlan:
    """
    Encapsulates everything the orchestrator and synthesis agent need to run
    a targeted, user-aware research session.

    Attributes:
        ticker: Stock ticker symbol (e.g. "AAPL").
        trade_type: One of "Day Trade", "Swing Trade", "Investment".
        selected_subject_ids: Ordered list of research subject IDs to run,
            sorted by priority (highest first).
        subject_focus: Mapping of subject_id → a one-paragraph focus hint
            derived from the user's stated concerns.  Empty string when no
            specific focus applies.
        trade_context: A concise summary of the user's goals / context,
            passed to the synthesis agent so it can frame the narrative.
        planner_reasoning: Internal reasoning from the planner LLM — logged
            to DB metadata but never injected into downstream prompts.
    """

    ticker: str
    trade_type: str
    selected_subject_ids: List[str] = field(default_factory=list)
    subject_focus: Dict[str, str] = field(default_factory=dict)
    trade_context: str = ""
    planner_reasoning: str = ""
    position_summary: str = ""  # Raw position block parsed from conversation_context
