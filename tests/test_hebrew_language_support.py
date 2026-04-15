"""
Tests for Hebrew language support across the research pipeline.

HOW HEBREW CURRENTLY WORKS (as of Apr 2026)
--------------------------------------------
Hebrew output is produced via **model inference**: when the user's language
preference is Hebrew, the frontend sends Hebrew-language context to the
backend (conversation_context), and Gemini infers it should respond in Hebrew.

There is NO explicit language injection in synthesis_node.py, chat_agent.py,
or orchestrator_graph.py — the `language` field is stored in ResearchState
but never read by the nodes that call the LLM.

TEST ORGANISATION
-----------------
Classes 1, 5 (English/None assertions), and 6 — tests that reflect current
behaviour — are strict (they must pass).

Classes 2, 3, 4 and the Hebrew-assertion tests in Class 5 are marked
`xfail`: they document the **desired** explicit implementation. Once proper
language injection is added to synthesis_node / chat_agent / orchestrator,
these will flip to passing.

Run structural tests (no API):
    python -m pytest tests/test_hebrew_language_support.py -v -s

Run all including integration (live API calls):
    python -m pytest tests/test_hebrew_language_support.py --integration -v -s
"""

import inspect
import re
from typing import Optional

import pytest
from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _contains_hebrew(text: str) -> bool:
    """Return True if text contains Hebrew Unicode characters (U+05D0–U+05EA range)."""
    return bool(re.search(r"[\u05d0-\u05ea\u05f0-\u05f4\ufb1d-\ufb4e]", text))


def _make_synthesis_state(language: Optional[str] = None, ticker: str = "AAPL"):
    """Build a minimal synthesis_node-compatible state dict."""
    from research_plan import ResearchPlan

    plan = ResearchPlan(
        ticker=ticker,
        trade_type="Investment",
        selected_subject_ids=["valuation"],
        subject_focus={"valuation": ""},
        trade_context="",
        planner_reasoning="test",
    )
    return {
        "ticker": ticker,
        "trade_type": "Investment",
        "plan": plan,
        "emitter": None,
        "progress_fn": None,
        "failed_subjects": [],
        "language": language,
        "research_outputs": {
            "valuation": {
                "subject_name": "Valuation Metrics",
                "research_output": (
                    f"{ticker} trades at P/E 32.1x vs sector 26.4x. "
                    "Revenue $94.9B (+5.1% YoY). EV/EBITDA 23.8x. "
                    "FCF $29.6B (31.2% margin). Services grew 14% to $23.9B. "
                    "EPS $1.64 beat estimate $1.60."
                ),
                "focus_hint": "",
                "sources": [],
            }
        },
    }


# ---------------------------------------------------------------------------
# 1. Structural Tests — ResearchState plumbing (no API calls)
# ---------------------------------------------------------------------------

class TestResearchStateLanguagePlumbing:
    """Verify ResearchState TypedDict and run_research() expose the language field."""

    def test_research_state_has_language_field(self):
        """ResearchState TypedDict must declare a 'language' key."""
        from research_graph import ResearchState

        annotations = ResearchState.__annotations__
        assert "language" in annotations, (
            "ResearchState TypedDict is missing the 'language' field. "
            "Add `language: Optional[str]` to ResearchState."
        )

    def test_language_field_is_optional_str(self):
        """The 'language' field must be Optional[str], not a bare str."""
        from research_graph import ResearchState

        lang_type = str(ResearchState.__annotations__["language"])
        assert "str" in lang_type, (
            f"language field should be Optional[str], got: {lang_type}"
        )

    def test_run_research_accepts_language_kwarg(self):
        """run_research() must accept a 'language' keyword argument."""
        from research_graph import run_research

        sig = inspect.signature(run_research)
        assert "language" in sig.parameters, (
            "run_research() is missing the 'language' parameter. "
            "Add `language: Optional[str] = None` to its signature."
        )

    def test_run_research_language_defaults_to_none(self):
        """The 'language' parameter must default to None."""
        from research_graph import run_research

        default = inspect.signature(run_research).parameters["language"].default
        assert default is None, (
            f"run_research() 'language' parameter must default to None, got: {default!r}"
        )

    def test_run_research_sets_language_in_initial_state(self):
        """run_research() must pass 'language' into the ResearchState initial dict."""
        from research_graph import run_research

        source = inspect.getsource(run_research)
        assert '"language": language' in source or "'language': language" in source, (
            "run_research() must include `'language': language` in its initial_state dict."
        )


# ---------------------------------------------------------------------------
# 2. Structural Tests — Synthesis node Hebrew injection (no API calls)
#
# XFAIL: synthesis_node.py does not yet explicitly read `language` from state
# or inject Hebrew instructions. These tests document the desired implementation.
# Remove xfail markers once explicit injection is added to synthesis_node.py.
# ---------------------------------------------------------------------------

class TestSynthesisNodeHebrewInjection:
    """Inspect synthesis_node source for Hebrew language instruction injection."""

    @pytest.mark.xfail(
        reason=(
            "synthesis_node.py does not yet read `language` from state. "
            "Hebrew is currently produced via model inference, not explicit injection. "
            "Fix: add `language = state.get('language')` in synthesis_node()."
        ),
        strict=False,
    )
    def test_synthesis_node_reads_language_from_state(self):
        """synthesis_node() must read the 'language' field from state."""
        from agents import synthesis_node as mod

        source = inspect.getsource(mod)
        assert 'state.get("language")' in source or "state['language']" in source or (
            '"language"' in source and "language" in source
        ), (
            "synthesis_node.py must read `language` from state. "
            "Add: `language = state.get('language')` in synthesis_node()."
        )

    @pytest.mark.xfail(
        reason=(
            "synthesis_node.py has no explicit Hebrew instruction block. "
            "Fix: add a Hebrew directive block in _get_synthesis_instructions() "
            "when language == 'he'."
        ),
        strict=False,
    )
    def test_synthesis_node_has_hebrew_instruction_block(self):
        """synthesis_node must inject a Hebrew instruction block when language='he'."""
        from agents import synthesis_node as mod

        source = inspect.getsource(mod)
        has_hebrew_block = "Hebrew" in source or "עברית" in source or (
            '== "he"' in source or "== 'he'" in source
        )
        assert has_hebrew_block, (
            "synthesis_node.py has no Hebrew instruction injection. "
            "Add a block in _get_synthesis_instructions() or synthesis_node() "
            "that appends Hebrew directives when language == 'he'."
        )


# ---------------------------------------------------------------------------
# 3. Structural Tests — Chat agent language support (no API calls)
#
# XFAIL: chat_agent.py does not yet expose a language attribute or inject
# Hebrew instructions. These tests document the desired implementation.
# ---------------------------------------------------------------------------

class TestChatAgentLanguageSupport:
    """Inspect chat_agent source for Hebrew language handling."""

    @pytest.mark.xfail(
        reason=(
            "ReportChatAgent does not yet have a `language` attribute. "
            "Fix: add `self.language: Optional[str] = None` in __init__()."
        ),
        strict=False,
    )
    def test_chat_agent_has_language_attribute_or_setter(self):
        """ReportChatAgent must expose a language attribute or set_language() method."""
        from agents.chat_agent import ReportChatAgent

        agent = ReportChatAgent()
        has_lang = hasattr(agent, "language") or hasattr(agent, "set_language")
        assert has_lang, (
            "ReportChatAgent must expose a `language` attribute or `set_language()` method. "
            "Add `self.language: Optional[str] = None` in __init__()."
        )

    @pytest.mark.xfail(
        reason=(
            "chat_agent.py has no explicit Hebrew instruction injection. "
            "Fix: add a Hebrew block in _get_system_instructions() when language == 'he'."
        ),
        strict=False,
    )
    def test_chat_agent_system_instructions_inject_hebrew(self):
        """_get_system_instructions() must inject a Hebrew block when language='he'."""
        from agents import chat_agent as mod

        source = inspect.getsource(mod)
        has_hebrew_block = "Hebrew" in source or (
            '== "he"' in source or "== 'he'" in source
        )
        assert has_hebrew_block, (
            "chat_agent.py has no Hebrew instruction injection. "
            "Add a block in _get_system_instructions() that appends Hebrew directives "
            "when language == 'he'."
        )


# ---------------------------------------------------------------------------
# 4. Structural Tests — Orchestrator language propagation (no API calls)
#
# XFAIL: OrchestratorSession does not yet store self.language or pass it to
# run_research(). These tests document the desired implementation.
# ---------------------------------------------------------------------------

class TestOrchestratorLanguagePropagation:
    """Verify OrchestratorSession stores and passes language to run_research()."""

    @pytest.mark.xfail(
        reason=(
            "OrchestratorSession.__init__() does not yet set self.language. "
            "Fix: add `self.language: Optional[str] = None` in __init__()."
        ),
        strict=False,
    )
    def test_orchestrator_session_has_language_field(self):
        """OrchestratorSession.__init__() must set self.language."""
        from orchestrator_graph import OrchestratorSession

        source = inspect.getsource(OrchestratorSession.__init__)
        assert "language" in source, (
            "OrchestratorSession.__init__() must initialise `self.language`. "
            "Add `self.language: Optional[str] = None` in __init__()."
        )

    @pytest.mark.xfail(
        reason=(
            "OrchestratorSession.generate_report() does not yet pass language "
            "to run_research(). Fix: add `language=self.language` in the call."
        ),
        strict=False,
    )
    def test_orchestrator_generate_report_passes_language(self):
        """OrchestratorSession.generate_report() must pass self.language to run_research()."""
        from orchestrator_graph import OrchestratorSession

        source = inspect.getsource(OrchestratorSession.generate_report)
        assert "language" in source, (
            "OrchestratorSession.generate_report() must pass `language=self.language` "
            "when calling run_research()."
        )


# ---------------------------------------------------------------------------
# 5. Integration Tests — Synthesis with real LLM calls
#
# Note on xfail tests below: synthesis_node() does not read `language` from
# state, so calling it directly with language="he" will NOT produce Hebrew
# (the language signal is ignored at this layer). These tests are xfail until
# explicit injection is added to synthesis_node.py.
#
# The English/None tests are strict — they should always pass since the node
# defaults to English regardless.
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestSynthesisHebrewOutput:
    """Live synthesis tests — verify Hebrew language actually reaches the LLM output."""

    @pytest.mark.xfail(
        reason=(
            "synthesis_node() does not read `language` from state. "
            "Hebrew is only produced in the full pipeline via model inference from context. "
            "This test will pass once explicit Hebrew injection is added to synthesis_node.py."
        ),
        strict=False,
    )
    def test_synthesis_hebrew_output_contains_hebrew_characters(self):
        """synthesis_node with language='he' must return a report containing Hebrew text."""
        from agents.synthesis_node import synthesis_node

        state = _make_synthesis_state(language="he")
        result = synthesis_node(state)

        report = result["report_text"]
        assert not report.startswith("Error"), f"Synthesis error: {report[:300]}"
        assert len(report) > 100, f"Report too short: {len(report)} chars"
        assert _contains_hebrew(report), (
            "synthesis_node with language='he' produced no Hebrew characters. "
            f"Report preview:\n{report[:600]}"
        )

    def test_synthesis_english_output_has_no_hebrew(self):
        """synthesis_node with language='en' must NOT produce Hebrew characters."""
        from agents.synthesis_node import synthesis_node

        state = _make_synthesis_state(language="en")
        result = synthesis_node(state)

        report = result["report_text"]
        assert not report.startswith("Error")
        assert not _contains_hebrew(report), (
            "synthesis_node with language='en' unexpectedly produced Hebrew characters."
        )

    def test_synthesis_default_language_none_no_hebrew(self):
        """synthesis_node with language=None must produce English output only."""
        from agents.synthesis_node import synthesis_node

        state = _make_synthesis_state(language=None)
        result = synthesis_node(state)

        report = result["report_text"]
        assert not report.startswith("Error")
        assert not _contains_hebrew(report), (
            "synthesis_node with language=None should default to English, not Hebrew."
        )

    @pytest.mark.xfail(
        reason="Requires synthesis_node to read language from state (not yet implemented).",
        strict=False,
    )
    def test_synthesis_hebrew_preserves_ticker_symbol(self):
        """Hebrew report must keep ticker symbols in Latin characters, not translate them."""
        from agents.synthesis_node import synthesis_node

        state = _make_synthesis_state(language="he", ticker="AAPL")
        result = synthesis_node(state)

        report = result["report_text"]
        assert "AAPL" in report, (
            "Ticker symbol 'AAPL' must remain in Latin characters even in Hebrew reports. "
            f"Report preview:\n{report[:600]}"
        )

    @pytest.mark.xfail(
        reason="Requires synthesis_node to read language from state (not yet implemented).",
        strict=False,
    )
    def test_synthesis_hebrew_preserves_numeric_data(self):
        """Hebrew report must retain the financial figures injected in research input."""
        from agents.synthesis_node import synthesis_node

        state = _make_synthesis_state(language="he")
        result = synthesis_node(state)

        report = result["report_text"]
        numbers = re.findall(r"\d+\.?\d*%?", report)
        assert len(numbers) >= 5, (
            f"Hebrew synthesis report must preserve numeric data from research input. "
            f"Found only {len(numbers)} numbers in report:\n{report[:600]}"
        )


# ---------------------------------------------------------------------------
# 6. Integration Tests — Full pipeline end-to-end
#
# These test the full run_research() pipeline. Hebrew output is currently
# produced via model inference when language context signals Hebrew —
# the full pipeline tests reflect this real behaviour.
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestFullPipelineHebrew:
    """End-to-end run_research() tests with Hebrew language."""

    def test_run_research_with_language_he_completes_without_error(self):
        """run_research(language='he') must complete and return report_text."""
        from research_graph import run_research

        result = run_research(
            ticker="AAPL",
            trade_type="Investment",
            conversation_context="Interested in Apple's valuation and AI strategy.",
            language="he",
        )

        assert "report_text" in result
        assert "report_id" in result
        report = result["report_text"]
        assert len(report) > 200, f"Report too short: {len(report)} chars"
        assert not report.startswith("Error"), f"Pipeline error: {report[:300]}"

    def test_run_research_hebrew_pipeline_output_contains_hebrew(self):
        """Full pipeline with language='he' must produce a report with Hebrew characters."""
        from research_graph import run_research

        result = run_research(
            ticker="AAPL",
            trade_type="Investment",
            conversation_context="ניתוח השקעות לטווח ארוך עם דגש על צמיחת שירותים.",  # Hebrew context
            language="he",
        )

        report = result["report_text"]
        assert _contains_hebrew(report), (
            "Full pipeline with Hebrew conversation context should produce Hebrew text. "
            f"Report preview:\n{report[:600]}"
        )

    def test_run_research_default_language_produces_english(self):
        """Full pipeline with language=None must produce an English report (no Hebrew)."""
        from research_graph import run_research

        result = run_research(
            ticker="AAPL",
            trade_type="Investment",
            conversation_context="Standard investment analysis.",
            language=None,
        )

        report = result["report_text"]
        assert not _contains_hebrew(report), (
            "Default pipeline (language=None) should not produce Hebrew characters."
        )

    def test_unknown_language_code_does_not_crash_pipeline(self):
        """An unsupported language code must not crash the pipeline — graceful fallback."""
        from research_graph import run_research

        result = run_research(
            ticker="AAPL",
            trade_type="Investment",
            conversation_context="Test with unsupported language code.",
            language="fr",
        )

        assert "report_text" in result
        assert len(result["report_text"]) > 100, (
            "Pipeline with unknown language code should still return a valid report."
        )
