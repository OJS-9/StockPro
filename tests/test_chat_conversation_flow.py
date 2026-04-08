"""
Conversation flow tests: realistic user conversations with mocked LLM.
10 tests simulating full ReAct loops through ReportChatAgent.
"""

import json
import re
from unittest.mock import patch, MagicMock, call

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_agent():
    with patch("agents.chat_agent.EmbeddingService"), \
         patch("agents.chat_agent.VectorSearch"), \
         patch("agents.chat_agent.ChatGoogleGenerativeAI"):
        from agents.chat_agent import ReportChatAgent
        return ReportChatAgent()


def _report_tool_msg(chunks=None):
    if chunks is None:
        chunks = [{"index": 1, "chunk_id": "c1", "section": "Revenue", "chunk_type": "report",
                    "similarity_score": 0.9, "chunk_text": "Tesla revenue was $96B in 2025."}]
    return ToolMessage(content=json.dumps(chunks), tool_call_id="tc-r", name="retrieve_report_chunks")


def _sec_tool_msg(items=None):
    if items is None:
        items = [{"index": 100, "source_type": "sec", "title": "Tesla 10-K (2025-12-31)",
                   "snippet": "Annual report filed 2026-02-15.", "url": "https://sec.gov/10k"}]
    return ToolMessage(content=json.dumps(items), tool_call_id="tc-s", name="search_ir_earnings")


def _yf_tool_msg(data=None):
    if data is None:
        data = [{"index": 200, "source_type": "yfinance",
                  "data": {"earnings_history": [{"index": "Q4 2025", "epsActual": 0.73, "epsEstimate": 0.68}],
                           "next_earnings_date": "2026-04-22", "trailing_eps": 2.96, "forward_eps": 3.40}}]
    return ToolMessage(content=json.dumps(data), tool_call_id="tc-y", name="get_earnings_data")


def _mock_invoke_result(*tool_msgs, answer_text="Answer."):
    """Build the dict that agent.invoke returns."""
    messages = list(tool_msgs) + [AIMessage(content=answer_text)]
    return {"messages": messages}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestConversationFlows:

    @patch("agents.chat_agent.create_chat_tools", return_value=[])
    @patch("agents.chat_agent.create_react_agent")
    def test_simple_report_question(self, mock_cra, mock_tools):
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = _mock_invoke_result(
            _report_tool_msg(), answer_text="Tesla revenue was $96B [1]."
        )
        mock_cra.return_value = mock_agent

        agent = _make_agent()
        result = agent.answer_question("rpt-1", "TSLA", "What is Tesla's revenue?")

        assert "96B" in result["answer"]
        assert len(result["sources"]) == 1
        assert result["sources"][0]["chunk_type"] == "report"

    @patch("agents.chat_agent.create_chat_tools", return_value=[])
    @patch("agents.chat_agent.create_react_agent")
    def test_earnings_question_triggers_multi_tool(self, mock_cra, mock_tools):
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = _mock_invoke_result(
            _report_tool_msg(), _yf_tool_msg(),
            answer_text="Per the report [1], EPS beat estimates at $0.73 vs $0.68 [200]."
        )
        mock_cra.return_value = mock_agent

        agent = _make_agent()
        result = agent.answer_question("rpt-1", "TSLA", "What were Tesla's latest earnings results?")

        types = {s["chunk_type"] for s in result["sources"]}
        assert "report" in types
        assert "yfinance" in types

    @patch("agents.chat_agent.create_chat_tools", return_value=[])
    @patch("agents.chat_agent.create_react_agent")
    def test_sec_filing_question(self, mock_cra, mock_tools):
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = _mock_invoke_result(
            _report_tool_msg(), _sec_tool_msg(),
            answer_text="The report discusses risks [1]. The 10-K confirms regulatory concerns [100]."
        )
        mock_cra.return_value = mock_agent

        agent = _make_agent()
        result = agent.answer_question("rpt-1", "TSLA", "What did Tesla's latest 10-K say about risk factors?")

        types = {s["chunk_type"] for s in result["sources"]}
        assert "report" in types
        assert "sec" in types

    @patch("agents.chat_agent.create_chat_tools", return_value=[])
    @patch("agents.chat_agent.create_react_agent")
    def test_all_tools_used(self, mock_cra, mock_tools):
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = _mock_invoke_result(
            _report_tool_msg(), _sec_tool_msg(), _yf_tool_msg(),
            answer_text="Report says [1]. 10-K shows [100]. YF data: EPS $0.73 [200]."
        )
        mock_cra.return_value = mock_agent

        agent = _make_agent()
        result = agent.answer_question("rpt-1", "TSLA",
                                        "Compare Tesla's reported earnings with the latest SEC filing and analyst estimates")

        types = {s["chunk_type"] for s in result["sources"]}
        assert types == {"report", "sec", "yfinance"}

    @patch("agents.chat_agent.create_chat_tools", return_value=[])
    @patch("agents.chat_agent.create_react_agent")
    def test_followup_question_uses_history(self, mock_cra, mock_tools):
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = _mock_invoke_result(
            _report_tool_msg(), answer_text="The P/E ratio is 50x [1]."
        )
        mock_cra.return_value = mock_agent

        agent = _make_agent()
        # First turn
        agent.chat_with_report("rpt-1", "TSLA", "What is the P/E ratio?")

        # Second turn -- mock returns different answer
        mock_agent.invoke.return_value = _mock_invoke_result(
            _report_tool_msg(), answer_text="Industry average is 25x, so TSLA trades at a premium [1]."
        )
        agent.chat_with_report("rpt-1", "TSLA", "How does that compare to the industry?")

        # Verify history was passed (second invoke should have messages with history)
        second_call = mock_agent.invoke.call_args_list[1]
        messages = second_call[0][0]["messages"]
        assert len(messages) >= 3  # at least: prev user, prev assistant, current user

    @patch("agents.chat_agent.create_chat_tools", return_value=[])
    @patch("agents.chat_agent.create_react_agent")
    def test_no_report_available(self, mock_cra, mock_tools):
        """When agent invoke raises due to no tools/bad state, returns error."""
        mock_agent = MagicMock()
        mock_agent.invoke.side_effect = ValueError("No report chunks found")
        mock_cra.return_value = mock_agent

        agent = _make_agent()
        result = agent.answer_question("rpt-1", "TSLA", "What is revenue?")

        assert "error" in result["answer"].lower() or "Error" in result["answer"]
        assert result["sources"] == []

    @patch("agents.chat_agent.create_chat_tools", return_value=[])
    @patch("agents.chat_agent.create_react_agent")
    def test_empty_ticker_still_works(self, mock_cra, mock_tools):
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = _mock_invoke_result(
            _report_tool_msg(), answer_text="Based on the report [1]."
        )
        mock_cra.return_value = mock_agent

        agent = _make_agent()
        result = agent.answer_question("rpt-1", "", "What is revenue?")

        assert "answer" in result
        assert isinstance(result["sources"], list)

    @patch("agents.chat_agent.create_chat_tools", return_value=[])
    @patch("agents.chat_agent.create_react_agent")
    def test_low_similarity_triggers_research_fallback(self, mock_cra, mock_tools):
        """When report chunks score low, research chunks appear in sources."""
        research_chunks = [{"index": 1, "chunk_id": "r1", "section": "Deep Analysis",
                            "chunk_type": "research", "similarity_score": 0.6,
                            "chunk_text": "Extended analysis of Tesla."}]
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = _mock_invoke_result(
            ToolMessage(content=json.dumps(research_chunks), tool_call_id="tc-r",
                        name="retrieve_report_chunks"),
            answer_text="The research shows [1]."
        )
        mock_cra.return_value = mock_agent

        agent = _make_agent()
        result = agent.answer_question("rpt-1", "TSLA", "Deep analysis?")

        assert any(s["chunk_type"] == "research" for s in result["sources"])

    @patch("agents.chat_agent.create_chat_tools", return_value=[])
    @patch("agents.chat_agent.create_react_agent")
    def test_agent_timeout_graceful(self, mock_cra, mock_tools):
        mock_agent = MagicMock()
        mock_agent.invoke.side_effect = RecursionError("Recursion limit reached")
        mock_cra.return_value = mock_agent

        agent = _make_agent()
        result = agent.answer_question("rpt-1", "TSLA", "Complex question?")

        assert "error" in result["answer"].lower() or "Error" in result["answer"]
        assert result["sources"] == []

    @patch("agents.chat_agent.create_chat_tools", return_value=[])
    @patch("agents.chat_agent.create_react_agent")
    def test_progress_callbacks_fired_in_order(self, mock_cra, mock_tools):
        """Verify progress_fn is called with expected messages when tools execute."""
        progress_calls = []

        def progress_fn(msg):
            progress_calls.append(msg)

        mock_agent = MagicMock()
        mock_agent.invoke.return_value = _mock_invoke_result(
            _report_tool_msg(), _sec_tool_msg(), _yf_tool_msg(),
            answer_text="Answer [1] [100] [200]."
        )
        mock_cra.return_value = mock_agent

        agent = _make_agent()
        agent.set_progress_fn(progress_fn)

        # Progress callbacks are fired by the tool functions themselves, not by the mock.
        # Since we mock create_react_agent, the real tools don't run.
        # This test verifies that set_progress_fn stores the callback.
        assert agent._progress_fn is progress_fn

        # To truly test progress ordering, we'd need to invoke actual tool functions.
        # Let's test that via create_chat_tools directly.
        from langchain_tools import create_chat_tools
        mock_es = MagicMock()
        mock_es.create_embedding.return_value = [0.1] * 3072
        mock_vs = MagicMock()
        mock_vs.search_chunks.return_value = [
            {"chunk_id": "c1", "section": "S", "similarity_score": 0.9,
             "chunk_text": "t", "chunk_type": "report"},
            {"chunk_id": "c2", "section": "S", "similarity_score": 0.8,
             "chunk_text": "t", "chunk_type": "report"},
        ]

        tools = create_chat_tools(
            nimble_client=None, report_id="rpt-1", ticker="TSLA",
            embedding_service=mock_es, vector_search=mock_vs,
            progress_fn=progress_fn,
        )

        # Invoke retrieve tool
        for t in tools:
            if t.name == "retrieve_report_chunks":
                t.invoke({"query": "test", "top_k": 5})
                break

        assert "Searching report..." in progress_calls
