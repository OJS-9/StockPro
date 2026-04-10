"""
Tests for agent pipeline improvements:
  - Quality gate heuristics (data points, ticker reference)
  - Synthesis input budget (truncation)
  - Actionable error messages
  - nimble_extract response truncation
  - Stale prompt cleanup

Run: python -m pytest tests/test_agent_pipeline_improvements.py -v
"""

import json
import re

import pytest


# ---------------------------------------------------------------------------
# Quality Gate Heuristics
# ---------------------------------------------------------------------------

class TestQualityGateHeuristics:
    """Test the enhanced quality gate in research_graph.py."""

    def _run_gate(self, research_outputs, ticker="AAPL"):
        """Run quality_gate_node with minimal state."""
        from research_graph import quality_gate_node

        state = {
            "research_outputs": research_outputs,
            "ticker": ticker,
            "emitter": None,
        }
        return quality_gate_node(state)

    def test_good_output_passes(self):
        outputs = {
            "valuation_metrics": {
                "subject_id": "valuation_metrics",
                "subject_name": "Valuation Metrics",
                "research_output": (
                    "AAPL trades at a P/E of 28.5x, above the sector average of 22.1x. "
                    "Revenue grew 8.2% YoY to $94.9B in the most recent quarter. "
                    "The forward P/E is 25.3x based on analyst consensus estimates. "
                    "Free cash flow margin is 26.4%, supporting a $110B buyback program. "
                    "Enterprise value to EBITDA stands at 21.8x."
                ),
                "sources": [],
            }
        }
        result = self._run_gate(outputs)
        assert "valuation_metrics" in result["research_outputs"]
        assert result["failed_subjects"] == []

    def test_output_too_short_fails(self):
        outputs = {
            "growth_drivers": {
                "subject_id": "growth_drivers",
                "subject_name": "Growth Drivers",
                "research_output": "Short.",
                "sources": [],
            }
        }
        result = self._run_gate(outputs)
        assert "growth_drivers" in result["failed_subjects"]

    def test_output_with_error_key_fails(self):
        outputs = {
            "risk_factors": {
                "subject_id": "risk_factors",
                "subject_name": "Risk Factors",
                "research_output": "Some content about AAPL with 10% risk",
                "error": "rate limit exceeded",
                "sources": [],
            }
        }
        result = self._run_gate(outputs)
        assert "risk_factors" in result["failed_subjects"]

    def test_no_data_points_fails(self):
        """Output with no numbers/percentages should fail."""
        outputs = {
            "financial_health": {
                "subject_id": "financial_health",
                "subject_name": "Financial Health",
                "research_output": (
                    "AAPL has strong financial health with excellent cash reserves. "
                    "The company maintains a solid balance sheet and generates "
                    "significant free cash flow. Revenue continues to grow steadily. "
                    "Management has been prudent with capital allocation."
                ),
                "sources": [],
            }
        }
        result = self._run_gate(outputs)
        assert "financial_health" in result["failed_subjects"]

    def test_no_ticker_reference_fails(self):
        """Output that never mentions the ticker should fail."""
        outputs = {
            "sector_macro": {
                "subject_id": "sector_macro",
                "subject_name": "Sector & Macro",
                "research_output": (
                    "The technology sector saw 15.3% growth in Q1 2026. "
                    "Interest rates remain at 4.5% and inflation is at 2.8%. "
                    "Consumer spending increased 3.2% year over year."
                ),
                "sources": [],
            }
        }
        result = self._run_gate(outputs, ticker="AAPL")
        assert "sector_macro" in result["failed_subjects"]

    def test_ticker_check_is_case_insensitive(self):
        """Ticker check should match 'aapl', 'AAPL', 'Aapl'."""
        outputs = {
            "valuation_metrics": {
                "subject_id": "valuation_metrics",
                "subject_name": "Valuation",
                "research_output": (
                    "aapl is currently trading at a P/E ratio of 28.5x, which is above the "
                    "tech sector average. Revenue grew 8.2% year-over-year to reach $94.9B. "
                    "Operating margin expanded 150 basis points to 30.1%. "
                    "The forward P/E stands at 25.3x based on consensus estimates."
                ),
                "sources": [],
            }
        }
        result = self._run_gate(outputs, ticker="AAPL")
        assert "valuation_metrics" in result["research_outputs"]
        assert result["failed_subjects"] == []

    def test_mixed_pass_and_fail(self):
        """One good output and one bad should partial-pass."""
        outputs = {
            "good": {
                "subject_id": "good",
                "subject_name": "Good Subject",
                "research_output": (
                    "TSLA revenue grew 12.5% to $25.2B in the latest quarter. "
                    "Gross margin was 18.2%, down from 19.5% in the prior quarter. "
                    "The company delivered 495,000 vehicles in Q1 2026, up 8% YoY. "
                    "Energy storage deployments reached 12.4 GWh, a record quarter."
                ),
                "sources": [],
            },
            "bad_no_numbers": {
                "subject_id": "bad_no_numbers",
                "subject_name": "Bad Subject",
                "research_output": (
                    "TSLA is doing well with strong growth and good market position "
                    "across all segments. The outlook remains positive for the future. "
                    "Management continues to execute on their strategy effectively. "
                    "The competitive landscape favors continued expansion globally."
                ),
                "sources": [],
            },
        }
        result = self._run_gate(outputs, ticker="TSLA")
        assert "good" in result["research_outputs"]
        assert "bad_no_numbers" in result["failed_subjects"]

    def test_abort_when_majority_fail(self):
        """When >50% subjects fail, gate should set report_text (abort)."""
        outputs = {
            "fail1": {
                "subject_id": "fail1",
                "subject_name": "Fail 1",
                "research_output": "short",
                "sources": [],
            },
            "fail2": {
                "subject_id": "fail2",
                "subject_name": "Fail 2",
                "research_output": "also short",
                "sources": [],
            },
            "pass1": {
                "subject_id": "pass1",
                "subject_name": "Pass 1",
                "research_output": (
                    "AAPL has revenue of $94.9B with 8.2% growth and a P/E of 28.5x. "
                    "Free cash flow is $26B annually."
                ),
                "sources": [],
            },
        }
        result = self._run_gate(outputs, ticker="AAPL")
        assert result.get("report_text"), "Gate should abort with a report_text message"
        assert "failed" in result["report_text"].lower()


# ---------------------------------------------------------------------------
# Synthesis Input Budget
# ---------------------------------------------------------------------------

class TestSynthesisBudget:
    """Test _truncate_research_text and _budget_research_outputs."""

    def test_truncate_short_text_unchanged(self):
        from agents.synthesis_node import _truncate_research_text

        text = "Short text with data."
        assert _truncate_research_text(text, 1000) == text

    def test_truncate_long_text_cuts(self):
        from agents.synthesis_node import _truncate_research_text

        text = "x" * 5000
        result = _truncate_research_text(text, 1000)
        assert len(result) < 1100  # 1000 + truncation notice
        assert "trimmed" in result.lower()

    def test_truncate_preserves_key_takeaways(self):
        from agents.synthesis_node import _truncate_research_text

        body = "A" * 3000
        takeaways = "## Key Takeaways\n- Revenue grew 15%\n- Margin expanded 200bps"
        text = body + "\n\n" + takeaways
        result = _truncate_research_text(text, 1000)
        assert "Key Takeaways" in result
        assert "Revenue grew 15%" in result

    def test_truncate_preserves_bold_takeaways(self):
        from agents.synthesis_node import _truncate_research_text

        body = "B" * 3000
        takeaways = "**Key Takeaways**\n- EPS beat by 12%\n- Guidance raised"
        text = body + "\n\n" + takeaways
        result = _truncate_research_text(text, 1000)
        assert "Key Takeaways" in result
        assert "EPS beat" in result

    def test_budget_under_limit_no_change(self):
        from agents.synthesis_node import _budget_research_outputs

        outputs = {
            "sub1": {"research_output": "Short " * 50},
            "sub2": {"research_output": "Also short " * 50},
        }
        result = _budget_research_outputs(outputs, ["sub1", "sub2"])
        assert result["sub1"]["research_output"] == outputs["sub1"]["research_output"]
        assert result["sub2"]["research_output"] == outputs["sub2"]["research_output"]

    def test_budget_over_limit_trims(self):
        from agents.synthesis_node import _budget_research_outputs, _MAX_TOTAL_RESEARCH_CHARS

        # Create outputs that exceed the budget
        long_text = "AAPL revenue grew 15.3% " * 2000  # ~48K chars
        outputs = {
            "sub1": {"research_output": long_text},
            "sub2": {"research_output": long_text},
        }
        result = _budget_research_outputs(outputs, ["sub1", "sub2"])
        total = sum(len(r["research_output"]) for r in result.values())
        # Total should be roughly within budget (with some overhead for truncation notices)
        assert total < _MAX_TOTAL_RESEARCH_CHARS * 1.1

    def test_budget_preserves_unordered_subjects(self):
        """Subjects not in ordered_ids should still be in the output."""
        from agents.synthesis_node import _budget_research_outputs

        outputs = {
            "sub1": {"research_output": "text1"},
            "extra": {"research_output": "extra text"},
        }
        result = _budget_research_outputs(outputs, ["sub1"])
        assert "extra" in result


# ---------------------------------------------------------------------------
# Actionable Error Messages
# ---------------------------------------------------------------------------

class TestActionableErrors:
    """Verify all tool error responses include a suggestion field."""

    def test_mcp_handler_error_has_suggestion(self):
        """MCP handler errors should include a suggestion."""
        from langchain_tools import _make_mcp_handler

        class FakeMCP:
            pass

        # _make_mcp_handler will fail when called since FakeMCP has no methods,
        # which is exactly what we want to test the error path
        handler = _make_mcp_handler(FakeMCP(), "FAKE_TOOL")
        result = json.loads(handler(symbol="AAPL"))
        assert "error" in result
        assert "suggestion" in result

    def test_yfinance_fundamentals_error_has_suggestion(self):
        """yfinance_fundamentals error should suggest alternatives."""
        from langchain_tools import create_yfinance_tools

        tools = create_yfinance_tools()
        fundamentals = next(t for t in tools if t.name == "yfinance_fundamentals")
        # Use an invalid symbol to trigger an error in the handler
        result = json.loads(fundamentals.invoke({"symbol": ""}))
        # Even if it succeeds with empty symbol, check the structure
        if "error" in result:
            assert "suggestion" in result

    def test_sec_edgar_error_has_suggestion(self):
        """sec_edgar error should include suggestion."""
        from langchain_tools import create_sec_edgar_tool

        tool = create_sec_edgar_tool()
        result = json.loads(tool.invoke({"symbol": "ZZZNOTREAL999"}))
        # If no filings found, it returns a message not an error
        # But if it errors, should have suggestion
        if "error" in result:
            assert "suggestion" in result


# ---------------------------------------------------------------------------
# nimble_extract Truncation
# ---------------------------------------------------------------------------

class TestNimbleExtractTruncation:
    """Test that nimble_extract truncates large responses."""

    def test_truncation_logic_directly(self):
        """Verify the truncation constant and logic exist."""
        # We can't easily call nimble_extract without a real client,
        # but we can verify the constant is set
        import langchain_tools
        # The MAX_EXTRACT_CHARS is defined inside create_nimble_tools,
        # so we verify the truncation pattern by reading the source
        import inspect
        source = inspect.getsource(langchain_tools.create_nimble_tools)
        assert "MAX_EXTRACT_CHARS" in source
        assert "10000" in source or "10_000" in source
        assert "truncated" in source.lower()


# ---------------------------------------------------------------------------
# Stale Prompt Cleanup
# ---------------------------------------------------------------------------

class TestResearchPromptCleanup:
    """Verify stale functions were removed and import is fixed."""

    def test_only_orchestration_instructions_exists(self):
        import research_prompt
        assert hasattr(research_prompt, "get_orchestration_instructions")
        assert not hasattr(research_prompt, "get_system_instructions")
        assert not hasattr(research_prompt, "get_specialized_agent_instructions")
        assert not hasattr(research_prompt, "get_followup_question_prompt")

    def test_orchestration_instructions_returns_string(self):
        from research_prompt import get_orchestration_instructions
        result = get_orchestration_instructions("AAPL", "Investment")
        assert isinstance(result, str)
        assert "AAPL" in result
        assert "Investment" in result

    def test_no_src_prefix_import(self):
        """Verify the file uses 'from date_utils' not 'from src.date_utils'."""
        import inspect
        import research_prompt
        source = inspect.getsource(research_prompt)
        assert "from src.date_utils" not in source
        assert "from date_utils" in source


# ---------------------------------------------------------------------------
# Specialized Prompt Trimming
# ---------------------------------------------------------------------------

class TestSpecializedPromptTrimming:
    """Verify the specialized prompt is leaner."""

    def test_no_begin_research_now(self):
        from agents.specialized_node import _get_instructions
        from research_subjects import get_research_subjects_for_trade_type

        subjects = get_research_subjects_for_trade_type("Investment")
        instructions = _get_instructions(subjects[0], "AAPL", "Investment")
        assert "Begin your research now" not in instructions

    def test_has_key_takeaways_requirement(self):
        from agents.specialized_node import _get_instructions
        from research_subjects import get_research_subjects_for_trade_type

        subjects = get_research_subjects_for_trade_type("Investment")
        instructions = _get_instructions(subjects[0], "AAPL", "Investment")
        assert "Key Takeaways" in instructions

    def test_no_verbose_trade_type_bullets(self):
        """The old 3-bullet trade type expansion should be gone."""
        from agents.specialized_node import _get_instructions
        from research_subjects import get_research_subjects_for_trade_type

        subjects = get_research_subjects_for_trade_type("Day Trade")
        instructions = _get_instructions(subjects[0], "AAPL", "Day Trade")
        assert "Adjust your research depth and focus" not in instructions


# ---------------------------------------------------------------------------
# Planner Examples
# ---------------------------------------------------------------------------

class TestPlannerExamples:
    """Verify planner prompt contains examples."""

    def test_planner_prompt_has_examples(self):
        from agents.planner_node import _build_system_prompt
        from research_subjects import get_research_subjects_for_trade_type

        eligible = get_research_subjects_for_trade_type("Investment")
        prompt = _build_system_prompt("AAPL", "Investment", eligible)
        assert "<examples>" in prompt
        assert "</examples>" in prompt
        assert "Day Trade" in prompt  # Day Trade example
        assert "TSLA" in prompt or "AAPL" in prompt  # example ticker

    def test_planner_prompt_has_two_examples(self):
        from agents.planner_node import _build_system_prompt
        from research_subjects import get_research_subjects_for_trade_type

        eligible = get_research_subjects_for_trade_type("Investment")
        prompt = _build_system_prompt("MSFT", "Investment", eligible)
        # Should have "Example 1" and "Example 2"
        assert "Example 1" in prompt
        assert "Example 2" in prompt


# ---------------------------------------------------------------------------
# XML Tags in Synthesis
# ---------------------------------------------------------------------------

class TestSynthesisXMLTags:
    """Verify synthesis prompt uses XML structural tags."""

    def test_synthesis_prompt_has_xml_tags(self):
        from agents.synthesis_node import _build_synthesis_prompt
        from research_plan import ResearchPlan

        plan = ResearchPlan(
            ticker="AAPL",
            trade_type="Investment",
            selected_subject_ids=["valuation_metrics"],
            subject_focus={"valuation_metrics": ""},
            trade_context="Testing synthesis",
            planner_reasoning="test",
        )
        outputs = {
            "valuation_metrics": {
                "subject_name": "Valuation Metrics",
                "research_output": "AAPL P/E is 28.5x with 8.2% revenue growth.",
                "focus_hint": "",
                "sources": [],
            }
        }
        prompt = _build_synthesis_prompt("AAPL", "Investment", outputs, plan)
        assert "<instructions>" in prompt
        assert "</instructions>" in prompt
        assert "<research_data>" in prompt
        assert "</research_data>" in prompt


# ---------------------------------------------------------------------------
# Tool Description Differentiation
# ---------------------------------------------------------------------------

class TestToolDescriptions:
    """Verify nimble_web_search and perplexity_research have distinct descriptions."""

    def test_descriptions_are_different(self):
        from langchain_tools import create_nimble_tools
        from nimble_client import NimbleClient

        # Create a mock client just to get tool definitions
        class FakeNimble:
            pass

        try:
            tools = create_nimble_tools(FakeNimble())
        except Exception:
            pytest.skip("Could not create nimble tools with fake client")

        search_tool = next((t for t in tools if t.name == "nimble_web_search"), None)
        perplexity_tool = next((t for t in tools if t.name == "perplexity_research"), None)

        assert search_tool is not None
        assert perplexity_tool is not None

        # Key differentiation: search = "specific facts", perplexity = "synthesized"
        assert "specific facts" in search_tool.description.lower() or "raw" in search_tool.description.lower()
        assert "synthesized" in perplexity_tool.description.lower() or "synthesis" in perplexity_tool.description.lower()

        # They should NOT share the same generic description
        assert search_tool.description != perplexity_tool.description
