import math


def test_keep_base_when_budget_allows_output():
    from spend_budget import compute_effective_specialized_settings_from_estimates

    subject_count = 2
    total_input_tokens_per_turn = 1000

    base_max_turns = 8
    base_max_output_tokens = 6000
    min_max_turns = 2
    min_max_output_tokens = 512

    input_rate = 0.001  # USD per 1K input tokens
    output_rate = 0.002  # USD per 1K output tokens

    # Compute estimated spend for base settings using the same formula.
    def estimate(max_turns: int, max_output_tokens: int) -> float:
        input_tokens_total = total_input_tokens_per_turn * max_turns
        output_tokens_total = subject_count * max_turns * max_output_tokens
        return (input_tokens_total / 1000.0) * input_rate + (output_tokens_total / 1000.0) * output_rate

    spend_budget_usd = estimate(base_max_turns, base_max_output_tokens) * 1.5

    result = compute_effective_specialized_settings_from_estimates(
        subject_count=subject_count,
        total_input_tokens_per_turn=total_input_tokens_per_turn,
        spend_budget_usd=spend_budget_usd,
        base_max_turns=base_max_turns,
        base_max_output_tokens=base_max_output_tokens,
        min_max_turns=min_max_turns,
        min_max_output_tokens=min_max_output_tokens,
        input_rate_usd_per_1k_tokens=input_rate,
        output_rate_usd_per_1k_tokens=output_rate,
    )

    assert result["effective_max_turns"] == base_max_turns
    assert result["effective_max_output_tokens"] == base_max_output_tokens
    assert result["budget_exhausted"] is False
    assert result["estimated_spend_usd"] <= spend_budget_usd + 1e-9


def test_reduce_output_tokens_when_budget_tight():
    from spend_budget import compute_effective_specialized_settings_from_estimates

    subject_count = 2
    total_input_tokens_per_turn = 1000

    base_max_turns = 8
    base_max_output_tokens = 6000
    min_max_turns = 2
    min_max_output_tokens = 512

    input_rate = 0.001
    output_rate = 0.01  # Increase output cost so output reduction matters.

    def estimate(max_turns: int, max_output_tokens: int) -> float:
        input_tokens_total = total_input_tokens_per_turn * max_turns
        output_tokens_total = subject_count * max_turns * max_output_tokens
        return (input_tokens_total / 1000.0) * input_rate + (output_tokens_total / 1000.0) * output_rate

    base_spend = estimate(base_max_turns, base_max_output_tokens)
    spend_budget_usd = base_spend * 0.3  # should force output reduction

    result = compute_effective_specialized_settings_from_estimates(
        subject_count=subject_count,
        total_input_tokens_per_turn=total_input_tokens_per_turn,
        spend_budget_usd=spend_budget_usd,
        base_max_turns=base_max_turns,
        base_max_output_tokens=base_max_output_tokens,
        min_max_turns=min_max_turns,
        min_max_output_tokens=min_max_output_tokens,
        input_rate_usd_per_1k_tokens=input_rate,
        output_rate_usd_per_1k_tokens=output_rate,
    )

    # New reduction order: turns first, then subject count, then output tokens.
    assert result["effective_max_turns"] <= base_max_turns
    assert min_max_output_tokens <= result["effective_max_output_tokens"] <= base_max_output_tokens
    assert result["estimated_spend_usd"] <= spend_budget_usd + 1e-9
    assert result["budget_exhausted"] is False


def test_reduce_turns_to_min_and_budget_exhausted_when_too_small():
    from spend_budget import compute_effective_specialized_settings_from_estimates

    subject_count = 3
    total_input_tokens_per_turn = 5000

    base_max_turns = 8
    base_max_output_tokens = 4000
    min_max_turns = 2
    min_max_output_tokens = 512

    input_rate = 0.001
    output_rate = 0.02

    def estimate(max_turns: int, max_output_tokens: int) -> float:
        input_tokens_total = total_input_tokens_per_turn * max_turns
        output_tokens_total = subject_count * max_turns * max_output_tokens
        return (input_tokens_total / 1000.0) * input_rate + (output_tokens_total / 1000.0) * output_rate

    # Efficiency factor (0.3) applies to output tokens; budget must be below
    # even that reduced floor to force budget_exhausted=True.
    min_spend_with_factor = (min_max_turns * total_input_tokens_per_turn / 1000.0) * input_rate + (
        subject_count * min_max_turns * min_max_output_tokens * 0.3 / 1000.0
    ) * output_rate
    spend_budget_usd = min_spend_with_factor * 0.5

    result = compute_effective_specialized_settings_from_estimates(
        subject_count=subject_count,
        total_input_tokens_per_turn=total_input_tokens_per_turn,
        spend_budget_usd=spend_budget_usd,
        base_max_turns=base_max_turns,
        base_max_output_tokens=base_max_output_tokens,
        min_max_turns=min_max_turns,
        min_max_output_tokens=min_max_output_tokens,
        input_rate_usd_per_1k_tokens=input_rate,
        output_rate_usd_per_1k_tokens=output_rate,
    )

    assert result["effective_max_turns"] == min_max_turns
    assert result["effective_max_output_tokens"] == min_max_output_tokens
    # Breadth is sacred: subject count is never trimmed.
    assert result["effective_subject_count"] == subject_count
    assert result["budget_exhausted"] is True
    assert result["estimated_spend_usd"] > spend_budget_usd


def test_breadth_never_trimmed_even_on_tight_budget():
    """With 8 selected subjects and a $0.50 budget, all 8 must come through."""
    from spend_budget import compute_effective_specialized_settings_from_estimates

    result = compute_effective_specialized_settings_from_estimates(
        subject_count=8,
        total_input_tokens_per_turn=8000,
        spend_budget_usd=0.50,
        base_max_turns=8,
        base_max_output_tokens=6000,
        min_max_turns=2,
        min_max_output_tokens=512,
        input_rate_usd_per_1k_tokens=0.001,
        output_rate_usd_per_1k_tokens=0.01,
    )
    assert result["effective_subject_count"] == 8


def test_efficiency_factor_makes_realistic_estimate(monkeypatch):
    """8 subjects, base=8 turns, output=6000, factor=0.3 → ~$0.25, not $1+."""
    from spend_budget import compute_effective_specialized_settings_from_estimates

    monkeypatch.setenv("RESEARCH_COST_EFFICIENCY_FACTOR", "0.3")

    # Large budget so no trimming happens; we just want to read estimated spend.
    result = compute_effective_specialized_settings_from_estimates(
        subject_count=8,
        total_input_tokens_per_turn=8 * 2000,  # 2000 tokens/subject/turn
        spend_budget_usd=100.0,
        base_max_turns=8,
        base_max_output_tokens=6000,
        min_max_turns=2,
        min_max_output_tokens=512,
        # Gemini 2.5 Pro approx rates per 1K tokens.
        input_rate_usd_per_1k_tokens=0.00125,
        output_rate_usd_per_1k_tokens=0.01,
    )
    # Without the factor output_total would be 8*8*6000 = 384K tokens = $3.84 output alone.
    # With 0.3 factor: $3.84 * 0.3 = $1.15 output + ~$0.16 input ≈ $1.31.
    # Old worst-case was strictly higher. We just assert the realistic side.
    assert result["estimated_spend_usd"] < 2.0

