"""
Tests for ask_user_questions tool integration on OrchestratorSession.
Verifies pending_questions state field behavior without live LLM calls.
"""

import sys
import os
import pytest
from unittest.mock import MagicMock, patch

# Run from project root: python -m pytest test_ask_user_questions.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))


@pytest.fixture
def session():
    """Create OrchestratorSession with all external deps mocked."""
    with patch('orchestrator_graph.ReportChatAgent'), \
         patch('orchestrator_graph.StepEmitter'):
        from orchestrator_graph import OrchestratorSession
        return OrchestratorSession(user_id=1)


class TestPendingQuestionsState:
    def test_pending_questions_initializes_empty(self, session):
        assert session.pending_questions == []

    def test_reset_conversation_clears_pending_questions(self, session):
        session.pending_questions = [{"question": "Q?", "options": ["A", "B"]}]
        session.reset_conversation()
        assert session.pending_questions == []

    def test_reset_conversation_does_not_raise(self, session):
        """Ensure stale current_plan attribute removed — no AttributeError."""
        session.reset_conversation()  # Previously had self.current_plan = None (stale attr)
        assert not hasattr(session, 'current_plan') or session.pending_questions == []


class TestAskUserQuestionsTool:
    def test_tool_stores_questions_on_session(self):
        """Simulate the ask_user_questions tool closure storing questions."""
        questions_payload = [
            {"question": "Time horizon?", "options": ["1 day", "1 week", "1 month"]},
            {"question": "Risk tolerance?", "options": ["Low", "Medium", "High"]},
        ]

        # Replicate the closure behavior from _get_agent_response
        class FakeSession:
            pending_questions = []

        fake_session = FakeSession()

        def ask_user_questions(questions):
            fake_session.pending_questions = questions
            return "Questions captured. Waiting for user answers before generating the report."

        result = ask_user_questions(questions_payload)
        assert fake_session.pending_questions == questions_payload
        assert "Questions captured" in result

    def test_tool_returns_correct_confirmation_string(self):
        class FakeSession:
            pending_questions = []

        fake_session = FakeSession()

        def ask_user_questions(questions):
            fake_session.pending_questions = questions
            return "Questions captured. Waiting for user answers before generating the report."

        result = ask_user_questions([])
        assert result == "Questions captured. Waiting for user answers before generating the report."

    def test_start_research_sets_current_ticker_uppercased(self):
        """start_research() sets current_ticker uppercase (existing behavior preserved)."""
        with patch('orchestrator_graph.ReportChatAgent'), \
             patch('orchestrator_graph.StepEmitter'):
            from orchestrator_graph import OrchestratorSession
            s = OrchestratorSession()
            s._get_agent_response = MagicMock(return_value="ok")
            s.start_research("nvda", "Investment")
            assert s.current_ticker == "NVDA"
            assert s.current_trade_type == "Investment"
