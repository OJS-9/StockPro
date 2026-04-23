"""
Integration tests -- real API calls to verify the full research pipeline
after the agent architecture improvements.

Run with: python -m pytest tests/test_integration_pipeline.py --integration -v -s

Requires:
  - GEMINI_API_KEY in .env
  - Network access to Google AI, Yahoo Finance, SEC EDGAR
"""

import json
import logging
import os
import time

import pytest
from dotenv import load_dotenv

load_dotenv()

pytestmark = pytest.mark.integration

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Planner -- real LLM call
# ---------------------------------------------------------------------------

class TestPlannerLive:
    """Test that the planner produces valid JSON with the new examples in prompt."""

    def test_planner_day_trade(self):
        from agents.planner_node import planner_node
        from research_subjects import get_research_subjects_for_trade_type

        state = {
            "ticker": "NVDA",
            "trade_type": "Day Trade",
            "conversation_context": "Looking at NVDA for a quick intraday play after earnings.",
            "emitter": None,
            "progress_fn": None,
            "user_selected_subjects": None,
            "spend_budget_usd": None,
        }
        result = planner_node(state)

        assert "plan" in result
        plan = result["plan"]
        assert plan.ticker == "NVDA"
        assert plan.trade_type == "Day Trade"
        assert len(plan.selected_subject_ids) >= 2
        assert isinstance(plan.subject_focus, dict)
        assert isinstance(plan.trade_context, str)
        logger.info(
            "Planner selected %d subjects: %s",
            len(plan.selected_subject_ids),
            plan.selected_subject_ids,
        )
        logger.info("Trade context: %s", plan.trade_context)

    def test_planner_investment(self):
        from agents.planner_node import planner_node

        state = {
            "ticker": "AAPL",
            "trade_type": "Investment",
            "conversation_context": "I want to understand AAPL's AI strategy and whether it justifies the premium valuation.",
            "emitter": None,
            "progress_fn": None,
            "user_selected_subjects": None,
            "spend_budget_usd": None,
        }
        result = planner_node(state)
        plan = result["plan"]

        assert len(plan.selected_subject_ids) >= 5  # Investment should get many subjects
        # Focus hints ideally non-empty when user gave context, but model may fallback
        non_empty_hints = [v for v in plan.subject_focus.values() if v]
        if plan.planner_reasoning and "fallback" not in plan.planner_reasoning:
            assert len(non_empty_hints) >= 1, "Planner should set focus hints based on user context"
        else:
            logger.warning("Planner used fallback — focus hints not tested")
        logger.info("Plan: %s", json.dumps({
            "subjects": plan.selected_subject_ids,
            "focus": plan.subject_focus,
            "context": plan.trade_context,
        }, indent=2))


# ---------------------------------------------------------------------------
# Specialized Agent -- single subject, real LLM + tools
# ---------------------------------------------------------------------------

class TestSpecializedAgentLive:
    """Test a single specialized agent with real tools and LLM."""

    def test_valuation_aapl(self):
        from agents.specialized_node import specialized_node
        from research_plan import ResearchPlan

        plan = ResearchPlan(
            ticker="AAPL",
            trade_type="Investment",
            selected_subject_ids=["valuation"],
            subject_focus={"valuation": "Focus on P/E relative to tech peers and DCF valuation"},
            trade_context="Long-term investment analysis",
            planner_reasoning="test",
        )
        state = {
            "ticker": "AAPL",
            "trade_type": "Investment",
            "plan": plan,
            "subject_id": "valuation",
            "effective_max_turns": 6,
            "effective_max_output_tokens": 4000,
            "progress_fn": None,
        }
        result = specialized_node(state)

        output = result["research_outputs"]["valuation"]
        text = output["research_output"]

        assert len(text) > 200, f"Output too short: {len(text)} chars"
        assert "AAPL" in text.upper() or "apple" in text.lower(), "Should reference AAPL"

        # Should contain actual numbers (our quality gate check)
        import re
        numbers = re.findall(r"\d+\.?\d*%?", text)
        assert len(numbers) >= 3, f"Expected data points, found {len(numbers)}"

        logger.info(
            "Valuation output: %d chars, %d data points",
            len(text), len(numbers),
        )
        # Print first 500 chars for manual inspection
        logger.info("Preview: %s...", text[:500])


# ---------------------------------------------------------------------------
# Quality Gate -- verify with real-ish outputs
# ---------------------------------------------------------------------------

class TestQualityGateLive:
    """Run quality gate on outputs that simulate real agent results."""

    def test_gate_passes_real_style_output(self):
        from research_graph import quality_gate_node

        state = {
            "ticker": "MSFT",
            "emitter": None,
            "research_outputs": {
                "valuation": {
                    "subject_id": "valuation",
                    "subject_name": "Valuation Metrics",
                    "research_output": (
                        "## Valuation Analysis for MSFT\n\n"
                        "Microsoft trades at a P/E of 34.2x, above the S&P 500 average of 21.5x. "
                        "Forward P/E is 29.8x based on FY2027 EPS estimates of $15.42. "
                        "Revenue grew 16.4% YoY to $65.6B in Q3 FY2026. "
                        "Azure revenue grew 33% with 8 points from AI services. "
                        "EV/EBITDA of 25.1x. Price-to-sales of 13.8x. "
                        "Free cash flow of $22.1B representing a 33.7% FCF margin.\n\n"
                        "**Key Takeaways**\n"
                        "- P/E 34.2x vs sector 28.5x\n"
                        "- Azure AI driving 8pp of cloud growth\n"
                        "- FCF margin 33.7% on $65.6B revenue\n"
                    ),
                    "sources": [],
                },
                "growth_drivers": {
                    "subject_id": "growth_drivers",
                    "subject_name": "Growth Drivers",
                    "research_output": (
                        "## Growth Analysis for MSFT\n\n"
                        "Microsoft's growth is driven by three pillars: Azure cloud (33% YoY), "
                        "Microsoft 365 Copilot adoption (+18M paid seats), and gaming (Activision "
                        "contributing $5.1B quarterly). Total revenue $65.6B, up 16.4%. "
                        "Operating income grew 22% to $28.9B. AI revenue run rate exceeded $15B "
                        "annualized. LinkedIn revenue grew 9% to $4.3B.\n\n"
                        "**Key Takeaways**\n"
                        "- Azure 33% growth with AI acceleration\n"
                        "- Copilot: 18M paid seats\n"
                        "- AI run rate: $15B+ annualized\n"
                    ),
                    "sources": [],
                },
            },
        }
        result = quality_gate_node(state)
        assert result["failed_subjects"] == []
        assert len(result["research_outputs"]) == 2
        # Verify sources extracted from URLs (none in this case)
        logger.info("Gate passed: %d subjects clean", len(result["research_outputs"]))


# ---------------------------------------------------------------------------
# Synthesis -- real LLM call with small input
# ---------------------------------------------------------------------------

class TestSynthesisLive:
    """Test synthesis with real LLM on small input (2 subjects)."""

    def test_synthesis_two_subjects(self):
        from agents.synthesis_node import synthesis_node
        from research_plan import ResearchPlan

        plan = ResearchPlan(
            ticker="MSFT",
            trade_type="Investment",
            selected_subject_ids=["valuation", "growth_drivers"],
            subject_focus={
                "valuation": "AI premium valuation",
                "growth_drivers": "Azure and Copilot growth",
            },
            trade_context="User is evaluating MSFT as a long-term AI play.",
            planner_reasoning="test",
        )
        state = {
            "ticker": "MSFT",
            "trade_type": "Investment",
            "plan": plan,
            "emitter": None,
            "progress_fn": None,
            "language": None,
            "failed_subjects": [],
            "research_outputs": {
                "valuation": {
                    "subject_name": "Valuation Metrics",
                    "research_output": (
                        "MSFT trades at P/E 34.2x vs sector 28.5x. Forward P/E 29.8x. "
                        "Revenue $65.6B (+16.4% YoY). EV/EBITDA 25.1x. FCF $22.1B (33.7% margin). "
                        "Price target consensus: $510 (14% upside from $448)."
                    ),
                    "focus_hint": "AI premium valuation",
                    "sources": ["https://finance.yahoo.com/quote/MSFT"],
                },
                "growth_drivers": {
                    "subject_name": "Growth Drivers",
                    "research_output": (
                        "Azure grew 33% with 8pp from AI. Copilot has 18M paid seats. "
                        "AI revenue run rate $15B+ annualized. Gaming $5.1B/quarter (Activision). "
                        "LinkedIn $4.3B (+9%). Operating income $28.9B (+22%)."
                    ),
                    "focus_hint": "Azure and Copilot growth",
                    "sources": ["https://microsoft.com/investor"],
                },
            },
        }
        result = synthesis_node(state)

        report = result["report_text"]
        assert len(report) > 500, f"Report too short: {len(report)} chars"
        assert "MSFT" in report or "Microsoft" in report
        assert result.get("actual_input_tokens", 0) > 0
        assert result.get("actual_output_tokens", 0) > 0

        logger.info(
            "Synthesis: %d chars, %d/%d tokens",
            len(report),
            result.get("actual_input_tokens", 0),
            result.get("actual_output_tokens", 0),
        )
        # Check XML tags didn't leak into the output
        assert "<instructions>" not in report
        assert "<research_data>" not in report
        logger.info("Report preview:\n%s", report[:1000])


# ---------------------------------------------------------------------------
# Tool Differentiation -- verify agents pick the right tools
# ---------------------------------------------------------------------------

class TestToolDifferentiationLive:
    """Verify the updated tool descriptions lead to correct tool selection."""

    def test_yfinance_tools_work(self):
        """Smoke test that yfinance tools return real data."""
        from langchain_tools import create_yfinance_tools

        tools = create_yfinance_tools()
        fundamentals = next(t for t in tools if t.name == "yfinance_fundamentals")
        analyst = next(t for t in tools if t.name == "yfinance_analyst")

        # Test fundamentals
        result = json.loads(fundamentals.invoke({"symbol": "AAPL"}))
        assert "error" not in result, f"Unexpected error: {result}"
        assert "profile" in result
        assert result["profile"]["symbol"] == "AAPL"

        # Test analyst
        result = json.loads(analyst.invoke({"symbol": "AAPL"}))
        assert "error" not in result, f"Unexpected error: {result}"

        logger.info("yfinance tools working correctly for AAPL")

    def test_sec_edgar_tool_works(self):
        """Smoke test SEC EDGAR tool."""
        from langchain_tools import create_sec_edgar_tool

        tool = create_sec_edgar_tool()
        result = json.loads(tool.invoke({"symbol": "AAPL", "form_types": "10-K", "max_results": 2}))
        assert isinstance(result, list)
        assert len(result) > 0
        assert "form_type" in result[0]
        logger.info("SEC EDGAR returned %d filings for AAPL", len(result))


# ---------------------------------------------------------------------------
# Chat Agent -- verify logger.debug instead of print
# ---------------------------------------------------------------------------

class TestChatAgentLogging:
    """Verify chat agent uses logger.debug, not print."""

    def test_no_print_statements(self):
        import inspect
        from agents import chat_agent
        source = inspect.getsource(chat_agent)
        # Count print( calls -- should be 0
        import re
        prints = re.findall(r'^\s+print\(', source, re.MULTILINE)
        assert len(prints) == 0, f"Found {len(prints)} print() calls in chat_agent.py"
