"""
Spend budget estimation + preflight budget-to-depth conversion.

The app doesn't currently track real token usage at runtime, so enforcement is
based on *estimated* USD cost using prompt-size heuristics.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


def _get_required_float_env(name: str) -> Optional[float]:
    raw = os.getenv(name)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def estimate_tokens(text: str) -> int:
    """
    Rough token estimator used across the project.

    Mirrors `src/report_chunker.py`:
    - 1 token ~= 4 characters
    """

    if not text:
        return 0
    return len(text) // 4


def get_spend_budget_usd(user_id: Optional[Any] = None) -> Optional[float]:
    """
    Return the per-run spend budget in USD.

    If `USER_BUDGET_USD_OVERRIDES_JSON` is set, it should be a JSON object
    mapping `user_id` (string) -> budget_usd.
    """

    default_budget = _get_required_float_env("RESEARCH_SPEND_BUDGET_USD_DEFAULT")
    if default_budget is None:
        # If budget isn't configured, treat it as "disabled".
        # We return None so we don't accidentally persist non-JSON values
        # (like Infinity) into MySQL JSON columns.
        return None

    overrides_raw = os.getenv("USER_BUDGET_USD_OVERRIDES_JSON")
    if user_id is None or not overrides_raw:
        return default_budget

    try:
        overrides = json.loads(overrides_raw)
        key = str(user_id)
        if isinstance(overrides, dict) and key in overrides:
            val = overrides.get(key)
            if val is not None:
                return float(val)
    except Exception:
        # If overrides are invalid, fall back to default.
        pass

    return default_budget


def get_gemini_usd_rates() -> Optional[Dict[str, float]]:
    """
    Returns USD rates per 1K tokens for Gemini:
    - input: `GEMINI_INPUT_USD_PER_1K_TOKENS`
    - output: `GEMINI_OUTPUT_USD_PER_1K_TOKENS`
    """

    input_rate = _get_required_float_env("GEMINI_INPUT_USD_PER_1K_TOKENS")
    output_rate = _get_required_float_env("GEMINI_OUTPUT_USD_PER_1K_TOKENS")

    if input_rate is None or output_rate is None:
        return None

    return {"input_rate": input_rate, "output_rate": output_rate}


def compute_effective_specialized_settings_from_estimates(
    *,
    subject_count: int,
    total_input_tokens_per_turn: int,
    spend_budget_usd: float,
    base_max_turns: int,
    base_max_output_tokens: int,
    min_max_turns: int,
    min_max_output_tokens: int,
    input_rate_usd_per_1k_tokens: float,
    output_rate_usd_per_1k_tokens: float,
    min_subject_count: int = 3,
) -> Dict[str, Any]:
    """
    Compute effective specialized depth (turns + subject count + output token caps)
    so the estimated spend stays within `spend_budget_usd`.

    Reduction order (quality-preserving):
      1. Reduce turns to minimum
      2. Reduce subject count (drop lowest-priority subjects first)
      3. Reduce output tokens (last resort, clamped to floor)

    Returns:
        - effective_max_turns
        - effective_max_output_tokens
        - effective_subject_count
        - estimated_spend_usd
        - budget_exhausted (bool)
    """

    subject_count = max(1, int(subject_count))
    total_input_tokens_per_turn = max(0, int(total_input_tokens_per_turn))

    base_max_turns = max(1, int(base_max_turns))
    base_max_output_tokens = max(1, int(base_max_output_tokens))

    min_max_turns = max(1, int(min_max_turns))
    min_max_output_tokens = max(1, int(min_max_output_tokens))
    min_subject_count = max(1, min(int(min_subject_count), subject_count))

    # Approximate input tokens per subject (used when subject count varies).
    input_per_subject_per_turn = (
        total_input_tokens_per_turn / subject_count if subject_count > 0 else 0
    )

    def estimate(turns: int, n_subjects: int, out_tokens: int) -> float:
        input_total = input_per_subject_per_turn * n_subjects * turns
        output_total = n_subjects * turns * out_tokens
        return (input_total / 1000.0) * input_rate_usd_per_1k_tokens + (
            output_total / 1000.0
        ) * output_rate_usd_per_1k_tokens

    # If we can't compute cost (rates missing) or budget is "infinite", keep defaults.
    if (
        spend_budget_usd == float("inf")
        or input_rate_usd_per_1k_tokens <= 0
        or output_rate_usd_per_1k_tokens <= 0
    ):
        return {
            "effective_max_turns": base_max_turns,
            "effective_max_output_tokens": base_max_output_tokens,
            "effective_subject_count": subject_count,
            "estimated_spend_usd": estimate(
                base_max_turns, subject_count, base_max_output_tokens
            ),
            "budget_exhausted": False,
        }

    # Step 1: base config fits → return unchanged.
    est = estimate(base_max_turns, subject_count, base_max_output_tokens)
    if est <= spend_budget_usd:
        return {
            "effective_max_turns": base_max_turns,
            "effective_max_output_tokens": base_max_output_tokens,
            "effective_subject_count": subject_count,
            "estimated_spend_usd": est,
            "budget_exhausted": False,
        }

    # Step 2: reduce turns to minimum, keep all subjects + base output.
    effective_turns = min_max_turns
    est = estimate(effective_turns, subject_count, base_max_output_tokens)
    if est <= spend_budget_usd:
        return {
            "effective_max_turns": effective_turns,
            "effective_max_output_tokens": base_max_output_tokens,
            "effective_subject_count": subject_count,
            "estimated_spend_usd": est,
            "budget_exhausted": False,
        }

    # Step 3: min turns, reduce subject count while keeping base output quality.
    for n in range(subject_count - 1, min_subject_count - 1, -1):
        est = estimate(effective_turns, n, base_max_output_tokens)
        if est <= spend_budget_usd:
            return {
                "effective_max_turns": effective_turns,
                "effective_max_output_tokens": base_max_output_tokens,
                "effective_subject_count": n,
                "estimated_spend_usd": est,
                "budget_exhausted": False,
            }

    # Step 4: last resort — min turns + min subjects, solve for output tokens.
    effective_subjects = min_subject_count
    input_cost = (
        input_per_subject_per_turn * effective_subjects * effective_turns / 1000.0
    ) * input_rate_usd_per_1k_tokens
    remaining = spend_budget_usd - input_cost
    if remaining <= 0:
        effective_out = min_max_output_tokens
    else:
        denom = (effective_subjects * effective_turns) * (
            output_rate_usd_per_1k_tokens / 1000.0
        )
        effective_out = int(remaining / denom) if denom > 0 else min_max_output_tokens
    effective_out = max(
        min_max_output_tokens, min(base_max_output_tokens, effective_out)
    )

    est = estimate(effective_turns, effective_subjects, effective_out)
    budget_exhausted = est > spend_budget_usd

    return {
        "effective_max_turns": effective_turns,
        "effective_max_output_tokens": effective_out,
        "effective_subject_count": effective_subjects,
        "estimated_spend_usd": est,
        "budget_exhausted": budget_exhausted,
    }


def _estimate_spend_usd(
    *,
    subject_count: int,
    total_input_tokens_per_turn: int,
    max_turns: int,
    max_output_tokens: int,
    input_rate_usd_per_1k_tokens: float,
    output_rate_usd_per_1k_tokens: float,
) -> float:
    input_tokens_total = total_input_tokens_per_turn * max_turns
    output_tokens_total = subject_count * max_turns * max_output_tokens

    input_cost = (input_tokens_total / 1000.0) * input_rate_usd_per_1k_tokens
    output_cost = (output_tokens_total / 1000.0) * output_rate_usd_per_1k_tokens
    return input_cost + output_cost


def _max_output_tokens_under_budget(
    *,
    subject_count: int,
    total_input_tokens_per_turn: int,
    turns: int,
    spend_budget_usd: float,
    input_rate_usd_per_1k_tokens: float,
    output_rate_usd_per_1k_tokens: float,
) -> int:
    """
    Solve output token cap for a fixed number of turns:

        budget = input_cost(turns) + output_cost(subject_count, turns, out)

    output_tokens_total = subject_count * turns * out
    """

    input_tokens_total = total_input_tokens_per_turn * turns
    input_cost = (input_tokens_total / 1000.0) * input_rate_usd_per_1k_tokens
    remaining = spend_budget_usd - input_cost
    if remaining <= 0:
        return 0

    denom = (subject_count * turns) * (output_rate_usd_per_1k_tokens / 1000.0)
    if denom <= 0:
        return 0

    # out <= remaining / ((subject_count * turns) * output_rate_per_1k / 1000)
    out = remaining / denom
    return int(out)


def compute_effective_specialized_settings_from_plan(
    *,
    ticker: str,
    trade_type: str,
    plan: Any,
    selected_subject_ids: List[str],
    spend_budget_usd: float,
) -> Dict[str, Any]:
    """
    Compute effective settings by:
    1) estimating prompt tokens for the selected subjects
    2) mapping budget -> effective turns/output-token caps
    """

    rates = get_gemini_usd_rates()
    if rates is None:
        # Budget enforcement disabled (can't compute USD without rates).
        return {
            "effective_max_turns": int(os.getenv("SPECIALIZED_AGENT_MAX_TURNS", "8")),
            "effective_max_output_tokens": int(
                os.getenv("SPECIALIZED_AGENT_MAX_OUTPUT_TOKENS", "6000")
            ),
            "effective_subject_count": len(selected_subject_ids),
            "estimated_spend_usd": None,
            "budget_exhausted": False,
        }

    input_rate = rates["input_rate"]
    output_rate = rates["output_rate"]

    base_max_turns = int(os.getenv("SPECIALIZED_AGENT_MAX_TURNS", "8"))
    base_max_output_tokens = int(
        os.getenv("SPECIALIZED_AGENT_MAX_OUTPUT_TOKENS", "6000")
    )

    min_max_turns = int(os.getenv("RESEARCH_SPEND_BUDGET_USD_MIN_MAX_TURNS", "2"))
    min_max_output_tokens = int(
        os.getenv("RESEARCH_SPEND_BUDGET_USD_MIN_MAX_OUTPUT_TOKENS", "512")
    )
    min_subject_count = int(os.getenv("RESEARCH_SPEND_BUDGET_USD_MIN_SUBJECTS", "3"))

    total_input_tokens_per_turn = estimate_total_input_tokens_per_turn(
        ticker=ticker,
        trade_type=trade_type,
        plan=plan,
        selected_subject_ids=selected_subject_ids,
    )

    return compute_effective_specialized_settings_from_estimates(
        subject_count=len(selected_subject_ids),
        total_input_tokens_per_turn=total_input_tokens_per_turn,
        spend_budget_usd=spend_budget_usd,
        base_max_turns=base_max_turns,
        base_max_output_tokens=base_max_output_tokens,
        min_max_turns=min_max_turns,
        min_max_output_tokens=min_max_output_tokens,
        input_rate_usd_per_1k_tokens=input_rate,
        output_rate_usd_per_1k_tokens=output_rate,
        min_subject_count=min_subject_count,
    )


def estimate_total_input_tokens_per_turn(
    *,
    ticker: str,
    trade_type: str,
    plan: Any,
    selected_subject_ids: List[str],
) -> int:
    """
    Estimate total "input tokens per LLM call per subject" across all subjects.

    This is used as a conservative linear input-cost multiplier when we reduce
    `effective_max_turns`.
    """

    from agents.specialized_node import _get_instructions
    from research_subjects import get_research_subject_by_id

    total = 0
    for sid in selected_subject_ids:
        subject = get_research_subject_by_id(sid)
        focus_hint = (
            getattr(plan, "subject_focus", {}).get(sid, "") if plan is not None else ""
        )

        instructions = _get_instructions(subject, ticker, trade_type, focus_hint)
        research_prompt = subject.prompt_template.format(ticker=ticker)
        if focus_hint:
            research_prompt += f"\n\nSpecific focus for this analysis: {focus_hint}"

        total += estimate_tokens(instructions + "\n" + research_prompt)

    return total
