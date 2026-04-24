"""End-to-end budget test: $1 cap, 8 user-picked subjects, verify all 8 come through."""

import os
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))
sys.path.insert(0, str(_project_root / "src"))

from dotenv import load_dotenv
load_dotenv()

os.environ["RESEARCH_SPEND_BUDGET_USD_DEFAULT"] = "1.0"

from research_graph import run_research

TICKER = "NVDA"
TRADE_TYPE = "Investment"
SUBJECTS = [
    "company_overview",
    "news_catalysts",
    "earnings_financials",
    "valuation",
    "revenue_breakdown",
    "growth_drivers",
    "risk_factors",
    "competitive_position",
]


def main():
    print(f"\n{'='*70}")
    print(f"E2E BUDGET TEST: {TICKER} | {TRADE_TYPE} | budget=$1.00 | 8 subjects")
    print(f"{'='*70}\n")

    from spend_budget import get_spend_budget_usd
    budget = get_spend_budget_usd()
    print(f"Budget read from env: ${budget}")

    result = run_research(
        ticker=TICKER,
        trade_type=TRADE_TYPE,
        conversation_context="Long-term investment thesis. Focus on moat, growth, risk.",
        selected_subjects=SUBJECTS,
        spend_budget_usd=budget,
    )

    outputs = result.get("research_outputs", {})
    report = result.get("report_text", "")

    print("\n--- RESULTS ---")
    print(f"effective_max_turns = {result.get('effective_max_turns')}")
    print(f"effective_max_output_tokens = {result.get('effective_max_output_tokens')}")
    print(f"effective_subject_count = {result.get('effective_subject_count')}")
    print(f"estimated_spend_usd = ${result.get('estimated_spend_usd')}")
    print(f"budget_exhausted = {result.get('budget_exhausted')}")
    print(f"actual_input_tokens = {result.get('actual_input_tokens')}")
    print(f"actual_output_tokens = {result.get('actual_output_tokens')}")
    print(f"failed_subjects = {result.get('failed_subjects')}")
    print(f"is_partial_report = {result.get('is_partial_report')}")

    print("\n--- PER-SUBJECT OUTPUT LENGTHS ---")
    all_nonempty = True
    for sid in SUBJECTS:
        entry = outputs.get(sid, {})
        out = entry.get("research_output", "")
        err = entry.get("error")
        status = "OK"
        if err:
            status = f"ERROR: {err[:80]}"
            all_nonempty = False
        elif not out.strip():
            status = "BLANK"
            all_nonempty = False
        elif len(out) < 200:
            status = f"SHORT ({len(out)} chars)"
        print(f"  [{status:20s}] {sid}: {len(out)} chars")

    print(f"\n--- VERIFICATION ---")
    print(f"  subject_count returned: {len(outputs)} (expected {len(SUBJECTS)})")
    print(f"  breadth preserved (all 8 present, non-empty): {all_nonempty}")
    print(f"  report length: {len(report)} chars")

    ok = (
        len(outputs) == len(SUBJECTS)
        and all_nonempty
        and result.get("effective_subject_count") == len(SUBJECTS)
    )
    print(f"\n{'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
