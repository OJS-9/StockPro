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

    assert result["effective_max_turns"] == base_max_turns, "Output should be reduced before turns."
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

    min_spend = estimate(min_max_turns, min_max_output_tokens)
    spend_budget_usd = min_spend * 0.8  # budget below even minimum

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
    assert result["budget_exhausted"] is True
    assert result["estimated_spend_usd"] > spend_budget_usd

