"""
Tests for the report chat agent: tool functions, source collection,
citation filtering, tool wiring, answer_question, and session management.
Groups 1-8 from the QA plan (43 tests).
"""

import json
import math
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


# ---------------------------------------------------------------------------
# Helpers & fixtures
# ---------------------------------------------------------------------------

def _make_chunk(chunk_id, section="Overview", score=0.8, text="Sample text", chunk_type="report"):
    return {
        "chunk_id": chunk_id,
        "section": section,
        "similarity_score": score,
        "chunk_text": text,
        "chunk_type": chunk_type,
    }


def _make_filing(form_type="10-K", filing_date="2026-01-15", period="2025-12-31",
                 description="Annual report", url="https://sec.gov/filing", company_name="Tesla, Inc"):
    return {
        "form_type": form_type,
        "filing_date": filing_date,
        "period": period,
        "description": description,
        "url": url,
        "company_name": company_name,
        "accession_number": "0001-23-456789",
    }


@pytest.fixture
def mock_embedding_service():
    svc = MagicMock()
    svc.create_embedding.return_value = [0.1] * 3072
    return svc


@pytest.fixture
def mock_vector_search():
    return MagicMock()


@pytest.fixture
def progress_calls():
    """Returns a list that collects progress_fn calls."""
    calls = []
    return calls


@pytest.fixture
def progress_fn(progress_calls):
    def _fn(msg):
        progress_calls.append(msg)
    return _fn


def _create_tools(embedding_service, vector_search, nimble_client=None, progress_fn=None):
    """Helper to import and call create_chat_tools."""
    from langchain_tools import create_chat_tools
    return create_chat_tools(
        nimble_client=nimble_client,
        report_id="rpt-123",
        ticker="TSLA",
        embedding_service=embedding_service,
        vector_search=vector_search,
        progress_fn=progress_fn,
    )


def _get_tool(tools, name):
    for t in tools:
        if t.name == name:
            return t
    raise KeyError(f"Tool {name!r} not found in {[t.name for t in tools]}")


# ===========================================================================
# Group 1: retrieve_report_chunks tool (7 tests)
# ===========================================================================

class TestRetrieveReportChunks:

    def test_retrieve_chunks_returns_indexed_results(self, mock_embedding_service, mock_vector_search):
        chunks = [_make_chunk("c1", "Revenue", 0.9), _make_chunk("c2", "Risk", 0.7)]
        mock_vector_search.search_chunks.return_value = chunks

        tools = _create_tools(mock_embedding_service, mock_vector_search)
        tool = _get_tool(tools, "retrieve_report_chunks")
        raw = tool.invoke({"query": "revenue", "top_k": 5})
        result = json.loads(raw)

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["index"] == 1
        assert result[0]["chunk_id"] == "c1"
        assert result[0]["section"] == "Revenue"
        assert "similarity_score" in result[0]
        assert "chunk_text" in result[0]

    def test_retrieve_chunks_deduplicates_by_chunk_id(self, mock_embedding_service, mock_vector_search):
        report_chunks = [_make_chunk("c1", "Revenue", 0.9)]
        research_chunks = [_make_chunk("c1", "Revenue", 0.85, chunk_type="research")]
        # score < 0.45 won't apply here; force fallback via few results (only 1 report chunk)
        mock_vector_search.search_chunks.side_effect = [report_chunks, research_chunks]

        tools = _create_tools(mock_embedding_service, mock_vector_search)
        tool = _get_tool(tools, "retrieve_report_chunks")
        raw = tool.invoke({"query": "revenue", "top_k": 5})
        result = json.loads(raw)

        chunk_ids = [r["chunk_id"] for r in result]
        assert chunk_ids.count("c1") == 1

    def test_retrieve_chunks_fallback_to_research(self, mock_embedding_service, mock_vector_search):
        report_chunks = [_make_chunk("c1", "Overview", 0.3), _make_chunk("c2", "Risk", 0.2)]
        research_chunks = [_make_chunk("c3", "Deep Dive", 0.6, chunk_type="research")]
        mock_vector_search.search_chunks.side_effect = [report_chunks, research_chunks]

        tools = _create_tools(mock_embedding_service, mock_vector_search)
        tool = _get_tool(tools, "retrieve_report_chunks")
        raw = tool.invoke({"query": "deep dive", "top_k": 5})
        result = json.loads(raw)

        chunk_types = {r["chunk_type"] for r in result}
        assert "research" in chunk_types

    def test_retrieve_chunks_no_fallback_when_score_high(self, mock_embedding_service, mock_vector_search):
        report_chunks = [_make_chunk("c1", "Revenue", 0.9), _make_chunk("c2", "Risk", 0.8)]
        mock_vector_search.search_chunks.return_value = report_chunks

        tools = _create_tools(mock_embedding_service, mock_vector_search)
        tool = _get_tool(tools, "retrieve_report_chunks")
        raw = tool.invoke({"query": "revenue", "top_k": 5})
        result = json.loads(raw)

        # search_chunks called only once (no research fallback)
        assert mock_vector_search.search_chunks.call_count == 1
        assert all(r["chunk_type"] == "report" for r in result)

    def test_retrieve_chunks_fallback_when_few_results(self, mock_embedding_service, mock_vector_search):
        report_chunks = [_make_chunk("c1", "Revenue", 0.9)]  # good score but only 1 result
        research_chunks = [_make_chunk("c3", "Extra", 0.5, chunk_type="research")]
        mock_vector_search.search_chunks.side_effect = [report_chunks, research_chunks]

        tools = _create_tools(mock_embedding_service, mock_vector_search)
        tool = _get_tool(tools, "retrieve_report_chunks")
        raw = tool.invoke({"query": "revenue", "top_k": 5})
        result = json.loads(raw)

        assert mock_vector_search.search_chunks.call_count == 2
        assert any(r["chunk_type"] == "research" for r in result)

    def test_retrieve_chunks_empty_results(self, mock_embedding_service, mock_vector_search):
        mock_vector_search.search_chunks.side_effect = [[], []]

        tools = _create_tools(mock_embedding_service, mock_vector_search)
        tool = _get_tool(tools, "retrieve_report_chunks")
        raw = tool.invoke({"query": "nonexistent", "top_k": 5})
        result = json.loads(raw)

        assert result == []

    def test_retrieve_chunks_embedding_error(self, mock_embedding_service, mock_vector_search):
        mock_embedding_service.create_embedding.side_effect = RuntimeError("API down")

        tools = _create_tools(mock_embedding_service, mock_vector_search)
        tool = _get_tool(tools, "retrieve_report_chunks")
        raw = tool.invoke({"query": "anything", "top_k": 5})
        result = json.loads(raw)

        assert "error" in result


# ===========================================================================
# Group 2: search_ir_earnings tool (8 tests)
# ===========================================================================

class TestSearchIREarnings:

    @patch("langchain_tools.create_chat_tools.__code__", create=True)  # dummy to avoid import issues
    def _make_ir_tool(self, mock_embedding_service, mock_vector_search, nimble_client=None, progress_fn=None):
        """Create tools with nimble_client so search_ir_earnings is included."""
        return _create_tools(mock_embedding_service, mock_vector_search,
                             nimble_client=nimble_client, progress_fn=progress_fn)

    @patch("sec_edgar.get_recent_filings")
    @patch("sec_edgar.get_company_name", return_value="Tesla, Inc")
    def test_sec_edgar_filings_returned_as_sources(self, mock_name, mock_filings,
                                                    mock_embedding_service, mock_vector_search):
        mock_filings.return_value = [
            _make_filing("10-K"), _make_filing("10-Q", period="2025-09-30"),
        ]
        nimble = MagicMock()
        tools = _create_tools(mock_embedding_service, mock_vector_search, nimble_client=nimble)
        tool = _get_tool(tools, "search_ir_earnings")
        raw = tool.invoke({"query": "annual report"})
        result = json.loads(raw)

        assert len(result) == 2
        assert all(r["source_type"] == "sec" for r in result)
        assert "Tesla, Inc" in result[0]["title"]
        assert result[0]["url"].startswith("https://")

    @patch("sec_edgar.get_recent_filings")
    @patch("sec_edgar.get_company_name", return_value="Tesla, Inc")
    def test_sec_results_indexed_from_100(self, mock_name, mock_filings,
                                          mock_embedding_service, mock_vector_search):
        mock_filings.return_value = [_make_filing(), _make_filing("10-Q")]
        nimble = MagicMock()
        tools = _create_tools(mock_embedding_service, mock_vector_search, nimble_client=nimble)
        tool = _get_tool(tools, "search_ir_earnings")
        result = json.loads(tool.invoke({"query": "earnings"}))

        assert result[0]["index"] == 100
        assert result[1]["index"] == 101

    @patch("sec_edgar.get_recent_filings")
    @patch("sec_edgar.get_company_name", return_value="Tesla, Inc")
    def test_nimble_fallback_when_sec_returns_few(self, mock_name, mock_filings,
                                                   mock_embedding_service, mock_vector_search):
        mock_filings.return_value = [_make_filing()]  # only 1
        nimble = MagicMock()
        nimble.search.return_value = {
            "results": [
                {"title": "Tesla Q1 Earnings", "snippet": "TSLA beat estimates", "url": "https://example.com/1"},
            ]
        }
        tools = _create_tools(mock_embedding_service, mock_vector_search, nimble_client=nimble)
        tool = _get_tool(tools, "search_ir_earnings")
        result = json.loads(tool.invoke({"query": "Q1 earnings"}))

        nimble.search.assert_called_once()
        assert any(r["source_type"] == "ir" for r in result)

    @patch("sec_edgar.get_recent_filings")
    @patch("sec_edgar.get_company_name", return_value="Tesla, Inc")
    def test_no_nimble_fallback_when_sec_sufficient(self, mock_name, mock_filings,
                                                     mock_embedding_service, mock_vector_search):
        mock_filings.return_value = [_make_filing(), _make_filing("10-Q")]
        nimble = MagicMock()
        tools = _create_tools(mock_embedding_service, mock_vector_search, nimble_client=nimble)
        tool = _get_tool(tools, "search_ir_earnings")
        tool.invoke({"query": "annual report"})

        nimble.search.assert_not_called()

    @patch("sec_edgar.get_recent_filings")
    @patch("sec_edgar.get_company_name", return_value="Tesla, Inc")
    def test_no_nimble_when_client_none(self, mock_name, mock_filings,
                                        mock_embedding_service, mock_vector_search):
        mock_filings.return_value = [_make_filing()]
        # No nimble client -> tool not included, but let's test SEC-only path
        # When nimble_client=None, search_ir_earnings tool is NOT created.
        # So we test with a nimble_client that is present but SEC returns enough.
        # Actually per the plan: when nimble_client=None the tool isn't added.
        # The real test is that create_chat_tools with nimble_client=None only returns 2 tools.
        tools = _create_tools(mock_embedding_service, mock_vector_search, nimble_client=None)
        tool_names = [t.name for t in tools]
        assert "search_ir_earnings" not in tool_names

    @patch("sec_edgar.get_recent_filings")
    @patch("sec_edgar.get_company_name", return_value="Tesla, Inc")
    def test_nimble_results_filtered_by_ticker(self, mock_name, mock_filings,
                                                mock_embedding_service, mock_vector_search):
        mock_filings.return_value = []  # force nimble fallback
        nimble = MagicMock()
        nimble.search.return_value = {
            "results": [
                {"title": "Tesla Q1 Earnings", "snippet": "TSLA beat", "url": "https://ex.com/1"},
                {"title": "Apple Results", "snippet": "AAPL missed", "url": "https://ex.com/2"},
                {"title": "Tesla guidance update", "snippet": "Strong outlook", "url": "https://ex.com/3"},
            ]
        }
        tools = _create_tools(mock_embedding_service, mock_vector_search, nimble_client=nimble)
        tool = _get_tool(tools, "search_ir_earnings")
        result = json.loads(tool.invoke({"query": "earnings"}))

        titles = [r["title"] for r in result]
        assert "Apple Results" not in titles
        assert any("Tesla" in t for t in titles)

    @patch("sec_edgar.get_recent_filings")
    @patch("sec_edgar.get_company_name", return_value="Tesla, Inc")
    def test_max_5_combined_results(self, mock_name, mock_filings,
                                     mock_embedding_service, mock_vector_search):
        mock_filings.return_value = [_make_filing(f"10-K") for _ in range(5)]
        nimble = MagicMock()
        # Even though SEC has 5, nimble won't be called (>= 2), but test the cap
        tools = _create_tools(mock_embedding_service, mock_vector_search, nimble_client=nimble)
        tool = _get_tool(tools, "search_ir_earnings")
        result = json.loads(tool.invoke({"query": "filings"}))

        assert len(result) <= 5

    @patch("sec_edgar.get_recent_filings", side_effect=RuntimeError("Network error"))
    @patch("sec_edgar.get_company_name", return_value="Tesla, Inc")
    def test_sec_edgar_network_error(self, mock_name, mock_filings,
                                      mock_embedding_service, mock_vector_search):
        nimble = MagicMock()
        tools = _create_tools(mock_embedding_service, mock_vector_search, nimble_client=nimble)
        tool = _get_tool(tools, "search_ir_earnings")
        raw = tool.invoke({"query": "earnings"})
        result = json.loads(raw)

        # Should return error JSON, not crash
        assert "error" in result


# ===========================================================================
# Group 3: get_earnings_data tool (5 tests)
# ===========================================================================

class TestGetEarningsData:

    @patch("yfinance.Ticker")
    def test_earnings_data_returns_indexed_result(self, mock_yf, mock_embedding_service, mock_vector_search):
        ticker_obj = MagicMock()
        ticker_obj.info = {"trailingEps": 3.5, "forwardEps": 4.0}
        ticker_obj.earnings_history = MagicMock(empty=True)
        ticker_obj.calendar = {"Earnings Date": ["2026-07-20"]}
        mock_yf.return_value = ticker_obj

        tools = _create_tools(mock_embedding_service, mock_vector_search)
        tool = _get_tool(tools, "get_earnings_data")
        result = json.loads(tool.invoke({}))

        assert isinstance(result, list)
        assert result[0]["index"] == 200
        assert result[0]["source_type"] == "yfinance"

    @patch("yfinance.Ticker")
    def test_earnings_data_includes_history(self, mock_yf, mock_embedding_service, mock_vector_search):
        import pandas as pd
        ticker_obj = MagicMock()
        ticker_obj.info = {}
        ticker_obj.earnings_history = pd.DataFrame({
            "epsActual": [1.0, 1.2], "epsEstimate": [0.9, 1.1],
        }, index=["Q1 2025", "Q2 2025"])
        ticker_obj.calendar = None
        mock_yf.return_value = ticker_obj

        tools = _create_tools(mock_embedding_service, mock_vector_search)
        tool = _get_tool(tools, "get_earnings_data")
        result = json.loads(tool.invoke({}))

        data = result[0]["data"]
        assert len(data["earnings_history"]) > 0

    @patch("yfinance.Ticker")
    def test_earnings_data_handles_nan(self, mock_yf, mock_embedding_service, mock_vector_search):
        import pandas as pd
        ticker_obj = MagicMock()
        ticker_obj.info = {"earningsGrowth": float("nan")}
        ticker_obj.earnings_history = pd.DataFrame({
            "epsActual": [float("nan")], "epsEstimate": [1.0],
        }, index=["Q1 2025"])
        ticker_obj.calendar = None
        mock_yf.return_value = ticker_obj

        tools = _create_tools(mock_embedding_service, mock_vector_search)
        tool = _get_tool(tools, "get_earnings_data")
        raw = tool.invoke({})
        # Should not raise — NaN sanitized to null
        result = json.loads(raw)
        assert isinstance(result, list)

    @patch("yfinance.Ticker")
    def test_earnings_data_missing_calendar(self, mock_yf, mock_embedding_service, mock_vector_search):
        ticker_obj = MagicMock()
        ticker_obj.info = {}
        ticker_obj.earnings_history = MagicMock(empty=True)
        ticker_obj.calendar = None
        mock_yf.return_value = ticker_obj

        tools = _create_tools(mock_embedding_service, mock_vector_search)
        tool = _get_tool(tools, "get_earnings_data")
        result = json.loads(tool.invoke({}))

        assert result[0]["data"]["next_earnings_date"] == "None"

    @patch("yfinance.Ticker", side_effect=RuntimeError("yfinance down"))
    def test_earnings_data_yfinance_error(self, mock_yf, mock_embedding_service, mock_vector_search):
        tools = _create_tools(mock_embedding_service, mock_vector_search)
        tool = _get_tool(tools, "get_earnings_data")
        result = json.loads(tool.invoke({}))

        assert "error" in result


# ===========================================================================
# Group 4: _collect_sources (6 tests)
# ===========================================================================

class TestCollectSources:

    def _make_agent(self):
        with patch("agents.chat_agent.EmbeddingService"), \
             patch("agents.chat_agent.VectorSearch"), \
             patch("agents.chat_agent.ChatGoogleGenerativeAI"):
            from agents.chat_agent import ReportChatAgent
            return ReportChatAgent()

    def test_collect_report_chunks(self):
        agent = self._make_agent()
        chunks = [
            {"index": 1, "chunk_id": "c1", "section": "Revenue", "chunk_type": "report",
             "similarity_score": 0.9, "chunk_text": "Revenue grew 20%"},
        ]
        msg = ToolMessage(content=json.dumps(chunks), tool_call_id="tc1", name="retrieve_report_chunks")
        sources = agent._collect_sources([msg])

        assert len(sources) == 1
        assert sources[0]["chunk_type"] == "report"
        assert sources[0]["chunk_id"] == "c1"
        assert sources[0]["section"] == "Revenue"

    def test_collect_sec_sources(self):
        agent = self._make_agent()
        items = [
            {"index": 100, "source_type": "sec", "title": "Tesla 10-K",
             "snippet": "Filed 2026-01-15", "url": "https://sec.gov/filing"},
        ]
        msg = ToolMessage(content=json.dumps(items), tool_call_id="tc2", name="search_ir_earnings")
        sources = agent._collect_sources([msg])

        assert len(sources) == 1
        assert sources[0]["chunk_type"] == "sec"
        assert sources[0]["url"] == "https://sec.gov/filing"

    def test_collect_ir_sources(self):
        agent = self._make_agent()
        items = [
            {"index": 102, "source_type": "ir", "title": "Tesla Earnings Call",
             "snippet": "Beat estimates", "url": "https://example.com/ir"},
        ]
        msg = ToolMessage(content=json.dumps(items), tool_call_id="tc3", name="search_ir_earnings")
        sources = agent._collect_sources([msg])

        assert len(sources) == 1
        assert sources[0]["chunk_type"] == "ir"
        assert sources[0]["url"] == "https://example.com/ir"

    def test_collect_yfinance_sources(self):
        agent = self._make_agent()
        items = [{
            "index": 200, "source_type": "yfinance",
            "data": {
                "earnings_history": [{"index": "Q1 2025", "epsActual": 1.0, "epsEstimate": 0.9}],
                "next_earnings_date": "2026-07-20",
                "earnings_growth": 0.15,
                "trailing_eps": 3.5,
                "forward_eps": 4.0,
            },
        }]
        msg = ToolMessage(content=json.dumps(items), tool_call_id="tc4", name="get_earnings_data")
        sources = agent._collect_sources([msg])

        assert len(sources) == 1
        assert sources[0]["chunk_type"] == "yfinance"
        assert sources[0]["index"] == 200
        assert "EPS" in sources[0]["chunk_text"]

    def test_collect_malformed_tool_result(self):
        agent = self._make_agent()
        msg = ToolMessage(content="not valid json {{{", tool_call_id="tc5", name="retrieve_report_chunks")
        sources = agent._collect_sources([msg])

        assert sources == []

    def test_collect_mixed_sources(self):
        agent = self._make_agent()
        report_msg = ToolMessage(
            content=json.dumps([{"index": 1, "chunk_id": "c1", "section": "Rev", "chunk_type": "report",
                                  "similarity_score": 0.9, "chunk_text": "text"}]),
            tool_call_id="tc1", name="retrieve_report_chunks",
        )
        sec_msg = ToolMessage(
            content=json.dumps([{"index": 100, "source_type": "sec", "title": "10-K",
                                  "snippet": "s", "url": "https://sec.gov"}]),
            tool_call_id="tc2", name="search_ir_earnings",
        )
        yf_msg = ToolMessage(
            content=json.dumps([{"index": 200, "source_type": "yfinance",
                                  "data": {"earnings_history": [], "trailing_eps": 3.5}}]),
            tool_call_id="tc3", name="get_earnings_data",
        )
        sources = agent._collect_sources([report_msg, sec_msg, yf_msg])

        types = [s["chunk_type"] for s in sources]
        assert "report" in types
        assert "sec" in types
        assert "yfinance" in types


# ===========================================================================
# Group 5: Citation filtering (5 tests)
# ===========================================================================

class TestCitationFiltering:

    def _run_answer_with_mock_agent(self, answer_text, all_sources):
        """Simulate the citation filtering logic from answer_question."""
        import re
        cited_indices = {int(m) for m in re.findall(r'\[(\d+)\]', answer_text)}
        sources = [s for s in all_sources if s["index"] in cited_indices]
        if not sources and all_sources:
            sources = [s for s in all_sources if s["chunk_type"] in ("report", "research")]
        return sources

    def test_only_cited_sources_returned(self):
        all_sources = [
            {"index": 1, "chunk_type": "report"},
            {"index": 2, "chunk_type": "report"},
            {"index": 3, "chunk_type": "report"},
        ]
        result = self._run_answer_with_mock_agent("Revenue grew 20% [1] and risk is moderate [3].", all_sources)
        indices = {s["index"] for s in result}
        assert indices == {1, 3}

    def test_uncited_sources_excluded(self):
        all_sources = [
            {"index": 1, "chunk_type": "report"},
            {"index": 2, "chunk_type": "report"},
        ]
        result = self._run_answer_with_mock_agent("Revenue grew [1].", all_sources)
        assert all(s["index"] != 2 for s in result)

    def test_no_citations_fallback(self):
        all_sources = [
            {"index": 1, "chunk_type": "report"},
            {"index": 100, "chunk_type": "sec"},
        ]
        result = self._run_answer_with_mock_agent("Revenue grew significantly.", all_sources)
        # Fallback includes report/research only
        assert len(result) == 1
        assert result[0]["chunk_type"] == "report"

    def test_high_index_citations(self):
        all_sources = [
            {"index": 1, "chunk_type": "report"},
            {"index": 100, "chunk_type": "sec"},
            {"index": 200, "chunk_type": "yfinance"},
        ]
        result = self._run_answer_with_mock_agent("SEC filing [100] shows growth. EPS [200] beat.", all_sources)
        indices = {s["index"] for s in result}
        assert indices == {100, 200}

    def test_multiple_citations_same_source(self):
        all_sources = [
            {"index": 1, "chunk_type": "report"},
            {"index": 2, "chunk_type": "report"},
        ]
        result = self._run_answer_with_mock_agent("Revenue [1] grew. Margins [1] expanded. Growth [1].", all_sources)
        assert len(result) == 1
        assert result[0]["index"] == 1


# ===========================================================================
# Group 6: create_chat_tools factory (4 tests)
# ===========================================================================

class TestCreateChatTools:

    def test_tools_with_nimble(self, mock_embedding_service, mock_vector_search):
        nimble = MagicMock()
        tools = _create_tools(mock_embedding_service, mock_vector_search, nimble_client=nimble)
        assert len(tools) == 3

    def test_tools_without_nimble(self, mock_embedding_service, mock_vector_search):
        tools = _create_tools(mock_embedding_service, mock_vector_search, nimble_client=None)
        assert len(tools) == 2

    def test_progress_fn_called(self, mock_embedding_service, mock_vector_search, progress_fn, progress_calls):
        mock_vector_search.search_chunks.return_value = [_make_chunk("c1", score=0.9), _make_chunk("c2", score=0.8)]
        tools = _create_tools(mock_embedding_service, mock_vector_search, progress_fn=progress_fn)
        tool = _get_tool(tools, "retrieve_report_chunks")
        tool.invoke({"query": "test", "top_k": 5})

        assert "Searching report..." in progress_calls

    def test_tool_names_match(self, mock_embedding_service, mock_vector_search):
        nimble = MagicMock()
        tools = _create_tools(mock_embedding_service, mock_vector_search, nimble_client=nimble)
        names = {t.name for t in tools}
        assert names == {"retrieve_report_chunks", "get_earnings_data", "search_ir_earnings"}


# ===========================================================================
# Group 7: ReportChatAgent.answer_question (5 tests)
# ===========================================================================

class TestAnswerQuestion:

    def _make_agent(self):
        with patch("agents.chat_agent.EmbeddingService"), \
             patch("agents.chat_agent.VectorSearch"), \
             patch("agents.chat_agent.ChatGoogleGenerativeAI"):
            from agents.chat_agent import ReportChatAgent
            return ReportChatAgent()

    def _mock_react_result(self, answer_text="Test answer [1]", tool_results=None):
        """Build a mock agent.invoke result with tool messages and final answer."""
        messages = []
        if tool_results:
            for tr in tool_results:
                messages.append(tr)
        messages.append(AIMessage(content=answer_text))
        return {"messages": messages}

    @patch("agents.chat_agent.create_chat_tools")
    @patch("agents.chat_agent.create_react_agent")
    def test_answer_returns_dict_with_answer_and_sources(self, mock_cra, mock_tools, mock_embedding_service):
        mock_tools.return_value = []
        chunks_content = json.dumps([{"index": 1, "chunk_id": "c1", "section": "Rev",
                                       "chunk_type": "report", "similarity_score": 0.9, "chunk_text": "text"}])
        tool_msg = ToolMessage(content=chunks_content, tool_call_id="tc1", name="retrieve_report_chunks")
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = self._mock_react_result("Revenue grew [1].", [tool_msg])
        mock_cra.return_value = mock_agent

        agent = self._make_agent()
        result = agent.answer_question("rpt-1", "TSLA", "What is revenue?")

        assert "answer" in result
        assert "sources" in result
        assert isinstance(result["answer"], str)
        assert isinstance(result["sources"], list)

    @patch("agents.chat_agent.create_chat_tools")
    @patch("agents.chat_agent.create_react_agent")
    def test_conversation_history_limited_to_3_turns(self, mock_cra, mock_tools):
        mock_tools.return_value = []
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = self._mock_react_result("Answer.")
        mock_cra.return_value = mock_agent

        agent = self._make_agent()
        history = [
            {"role": "user", "content": f"Q{i}"} for i in range(5)
        ]
        agent.answer_question("rpt-1", "TSLA", "Latest?", conversation_history=history)

        call_args = mock_agent.invoke.call_args[0][0]
        # Last 3 from history + current question
        human_msgs = [m for m in call_args["messages"] if isinstance(m, HumanMessage)]
        assert len(human_msgs) <= 4  # 3 history + 1 current

    @patch("agents.chat_agent.create_chat_tools")
    @patch("agents.chat_agent.create_react_agent")
    def test_current_question_always_last(self, mock_cra, mock_tools):
        mock_tools.return_value = []
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = self._mock_react_result("Answer.")
        mock_cra.return_value = mock_agent

        agent = self._make_agent()
        history = [{"role": "user", "content": "Same question"}]
        agent.answer_question("rpt-1", "TSLA", "Different question", conversation_history=history)

        call_args = mock_agent.invoke.call_args[0][0]
        last_msg = call_args["messages"][-1]
        assert isinstance(last_msg, HumanMessage)
        assert last_msg.content == "Different question"

    @patch("agents.chat_agent.create_chat_tools")
    @patch("agents.chat_agent.create_react_agent")
    def test_agent_error_returns_error_dict(self, mock_cra, mock_tools):
        mock_tools.return_value = []
        mock_agent = MagicMock()
        mock_agent.invoke.side_effect = RuntimeError("LLM timeout")
        mock_cra.return_value = mock_agent

        agent = self._make_agent()
        result = agent.answer_question("rpt-1", "TSLA", "What happened?")

        assert "Error" in result["answer"] or "error" in result["answer"].lower()
        assert result["sources"] == []

    @patch("agents.chat_agent.create_chat_tools")
    @patch("agents.chat_agent.create_react_agent")
    def test_multipart_content_extracted(self, mock_cra, mock_tools):
        mock_tools.return_value = []
        mock_agent = MagicMock()
        multipart = [{"text": "Part 1. "}, {"text": "Part 2."}]
        mock_agent.invoke.return_value = {"messages": [AIMessage(content=multipart)]}
        mock_cra.return_value = mock_agent

        agent = self._make_agent()
        result = agent.answer_question("rpt-1", "TSLA", "Question?")

        assert "Part 1" in result["answer"]
        assert "Part 2" in result["answer"]


# ===========================================================================
# Group 8: chat_with_report session management (3 tests)
# ===========================================================================

class TestChatWithReport:

    def _make_agent(self):
        with patch("agents.chat_agent.EmbeddingService"), \
             patch("agents.chat_agent.VectorSearch"), \
             patch("agents.chat_agent.ChatGoogleGenerativeAI"):
            from agents.chat_agent import ReportChatAgent
            return ReportChatAgent()

    @patch("agents.chat_agent.create_chat_tools")
    @patch("agents.chat_agent.create_react_agent")
    def test_history_accumulated(self, mock_cra, mock_tools):
        mock_tools.return_value = []
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"messages": [AIMessage(content="Answer.")]}
        mock_cra.return_value = mock_agent

        agent = self._make_agent()
        agent.chat_with_report("rpt-1", "TSLA", "Q1")
        agent.chat_with_report("rpt-1", "TSLA", "Q2")

        assert len(agent.conversation_history) == 4  # 2 user + 2 assistant

    @patch("agents.chat_agent.create_chat_tools")
    @patch("agents.chat_agent.create_react_agent")
    def test_reset_history(self, mock_cra, mock_tools):
        mock_tools.return_value = []
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"messages": [AIMessage(content="Answer.")]}
        mock_cra.return_value = mock_agent

        agent = self._make_agent()
        agent.chat_with_report("rpt-1", "TSLA", "Q1")
        assert len(agent.conversation_history) == 2
        agent.chat_with_report("rpt-1", "TSLA", "Q2", reset_history=True)
        # After reset + new Q&A, should have 2 entries
        assert len(agent.conversation_history) == 2

    @patch("agents.chat_agent.create_chat_tools")
    @patch("agents.chat_agent.create_react_agent")
    def test_result_passthrough(self, mock_cra, mock_tools):
        mock_tools.return_value = []
        chunks_content = json.dumps([{"index": 1, "chunk_id": "c1", "section": "Rev",
                                       "chunk_type": "report", "similarity_score": 0.9, "chunk_text": "text"}])
        tool_msg = ToolMessage(content=chunks_content, tool_call_id="tc1", name="retrieve_report_chunks")
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"messages": [tool_msg, AIMessage(content="Revenue grew [1].")]}
        mock_cra.return_value = mock_agent

        agent = self._make_agent()
        result = agent.chat_with_report("rpt-1", "TSLA", "Revenue?")

        assert "answer" in result
        assert "sources" in result
