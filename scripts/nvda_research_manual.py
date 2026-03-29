"""
Test research call: NVDA, Investment trade type.
Runs the full pipeline: PlannerAgent → ResearchOrchestrator → SynthesisAgent.
Run from project root: python test_nvda_research.py
"""

import sys
import os

# Add src to path so relative imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from dotenv import load_dotenv
load_dotenv()

from agent import StockResearchAgent

TICKER = "NVDA"
TRADE_TYPE = "Investment"

def main():
    print(f"\n{'='*60}")
    print(f"TEST: {TICKER} | {TRADE_TYPE}")
    print(f"{'='*60}\n")

    agent = StockResearchAgent()
    agent.current_ticker = TICKER
    agent.current_trade_type = TRADE_TYPE

    report = agent.generate_report(context="Long-term investment thesis. Focus on growth drivers, margin structure, and competitive position.")

    print(f"\n{'='*60}")
    print("FINAL REPORT")
    print(f"{'='*60}\n")
    print(report)

    # Spot-check key signals from the new prompts
    checks = [
        ("Growth decomposition framework", any(kw in report for kw in ["Volume", "Price × Mix", "NRR", "TPV", "CAGR"])),
        ("Margin tree language", any(kw in report for kw in ["Gross →", "EBITDA", "FCF", "margin tree", "operating leverage"])),
        ("Moat framework", any(kw in report for kw in ["switching cost", "network effect", "moat", "Switching cost"])),
        ("Key Takeaways section", "Key Takeaways" in report),
        ("Quantified claims (% or $)", any(c in report for c in ["%", "$", "YoY", "bps"])),
    ]

    print(f"\n{'='*60}")
    print("SPOT CHECKS")
    print(f"{'='*60}")
    all_pass = True
    for label, passed in checks:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{status}] {label}")

    print(f"\n{'='*60}")
    print(f"Result: {'ALL CHECKS PASSED' if all_pass else 'SOME CHECKS FAILED'}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
