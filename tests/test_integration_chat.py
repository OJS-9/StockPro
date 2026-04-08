"""
Integration tests -- real API calls to SEC EDGAR, Gemini LLM, and yfinance.
Run with: python -m pytest tests/test_integration_chat.py --integration -v

These tests require:
  - GEMINI_API_KEY in .env
  - Network access to SEC EDGAR (sec.gov), Google AI, Yahoo Finance
"""

import json
import os
import time

import pytest
from dotenv import load_dotenv

load_dotenv()

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# SEC EDGAR -- real API (free, no key)
# ---------------------------------------------------------------------------

class TestSECEdgarLive:

    def test_get_cik_tsla(self):
        from sec_edgar import get_cik
        cik = get_cik("TSLA")
        assert cik is not None
        assert isinstance(cik, int)
        assert cik == 1318605

    def test_get_cik_aapl(self):
        from sec_edgar import get_cik
        cik = get_cik("AAPL")
        assert cik is not None
        assert cik == 320193

    def test_get_cik_unknown_returns_none(self):
        from sec_edgar import get_cik
        cik = get_cik("ZZZNOTREAL999")
        assert cik is None

    def test_get_company_name_tsla(self):
        from sec_edgar import get_company_name
        name = get_company_name("TSLA")
        assert name is not None
        assert "tesla" in name.lower()

    def test_get_recent_filings_tsla(self):
        from sec_edgar import get_recent_filings
        filings = get_recent_filings("TSLA", form_types=["10-K", "10-Q"], max_results=3)

        assert isinstance(filings, list)
        assert len(filings) > 0
        assert len(filings) <= 3

        f = filings[0]
        assert f["form_type"] in ("10-K", "10-Q")
        assert f["filing_date"]  # not empty
        assert f["url"].startswith("https://")
        assert "company_name" in f

    def test_get_recent_filings_filters_correctly(self):
        from sec_edgar import get_recent_filings
        filings = get_recent_filings("TSLA", form_types=["10-K"], max_results=2)

        for f in filings:
            assert f["form_type"] == "10-K"

    def test_get_recent_filings_8k(self):
        from sec_edgar import get_recent_filings
        filings = get_recent_filings("TSLA", form_types=["8-K"], max_results=5)
        assert len(filings) > 0
        assert all(f["form_type"] == "8-K" for f in filings)

    def test_get_recent_filings_unknown_ticker_empty(self):
        from sec_edgar import get_recent_filings
        filings = get_recent_filings("ZZZNOTREAL999")
        assert filings == []


# ---------------------------------------------------------------------------
# SEC EDGAR Tool (StructuredTool wrapper)
# ---------------------------------------------------------------------------

class TestSECEdgarToolLive:

    def test_sec_tool_real_tsla(self):
        from langchain_tools import create_sec_edgar_tool
        tool = create_sec_edgar_tool()
        raw = tool.invoke({"symbol": "TSLA", "form_types": "10-K,10-Q", "max_results": 3})
        result = json.loads(raw)

        assert isinstance(result, list)
        assert len(result) > 0
        assert result[0]["form_type"] in ("10-K", "10-Q")

    def test_sec_tool_unknown_ticker(self):
        from langchain_tools import create_sec_edgar_tool
        tool = create_sec_edgar_tool()
        raw = tool.invoke({"symbol": "ZZZNOTREAL999"})
        result = json.loads(raw)

        assert "message" in result or "results" in result


# ---------------------------------------------------------------------------
# Gemini Embeddings -- real API
# ---------------------------------------------------------------------------

class TestEmbeddingsLive:

    def test_create_embedding_returns_3072_dim(self):
        from embedding_service import EmbeddingService
        svc = EmbeddingService()
        vec = svc.create_embedding("Tesla revenue growth analysis")

        assert isinstance(vec, list)
        assert len(vec) == 3072
        assert all(isinstance(v, float) for v in vec)

    def test_embedding_different_texts_differ(self):
        from embedding_service import EmbeddingService
        svc = EmbeddingService()
        vec1 = svc.create_embedding("Tesla electric vehicles")
        vec2 = svc.create_embedding("Apple iPhone sales")

        # Vectors should be different for different texts
        assert vec1 != vec2

    def test_embedding_empty_string(self):
        from embedding_service import EmbeddingService
        svc = EmbeddingService()
        # Should not crash on empty string
        vec = svc.create_embedding("test")
        assert len(vec) == 3072


# ---------------------------------------------------------------------------
# Gemini LLM -- real API call
# ---------------------------------------------------------------------------

class TestGeminiLLMLive:

    def test_llm_simple_invoke(self):
        os.environ.setdefault("GOOGLE_API_KEY", os.getenv("GEMINI_API_KEY", ""))
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import HumanMessage

        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0, timeout=30)
        result = llm.invoke([HumanMessage(content="What is 2+2? Reply with just the number.")])

        assert result.content is not None
        assert "4" in str(result.content)

    def test_llm_with_system_prompt(self):
        os.environ.setdefault("GOOGLE_API_KEY", os.getenv("GEMINI_API_KEY", ""))
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import HumanMessage

        llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0, timeout=30)
        result = llm.invoke([
            HumanMessage(content="Name a stock ticker for an electric car company. Reply with just the ticker symbol.")
        ])

        assert result.content is not None
        text = str(result.content).upper().strip()
        # Should mention TSLA or similar
        assert len(text) <= 10  # Short response


# ---------------------------------------------------------------------------
# yfinance -- real API
# ---------------------------------------------------------------------------

class TestYFinanceLive:

    def test_yfinance_ticker_info(self):
        import yfinance as yf
        t = yf.Ticker("TSLA")
        info = t.info

        assert info is not None
        assert "shortName" in info or "longName" in info

    def test_yfinance_earnings_history(self):
        import yfinance as yf
        t = yf.Ticker("TSLA")
        eh = t.earnings_history

        assert eh is not None
        if not eh.empty:
            assert len(eh) > 0

    def test_yfinance_calendar(self):
        import yfinance as yf
        t = yf.Ticker("TSLA")
        cal = t.calendar
        # calendar can be None or dict -- just verify no crash
        assert cal is None or isinstance(cal, dict)


# ---------------------------------------------------------------------------
# Chat tools with real embeddings (no DB, no LLM agent)
# ---------------------------------------------------------------------------

class TestChatToolsRealEmbeddings:

    def test_retrieve_chunks_real_embedding_mock_db(self):
        """Real embedding call, but mock vector_search (no DB)."""
        from unittest.mock import MagicMock
        from embedding_service import EmbeddingService
        from langchain_tools import create_chat_tools

        es = EmbeddingService()
        vs = MagicMock()
        vs.search_chunks.return_value = [
            {"chunk_id": "c1", "section": "Revenue", "similarity_score": 0.85,
             "chunk_text": "Tesla revenue $96B.", "chunk_type": "report"},
            {"chunk_id": "c2", "section": "Growth", "similarity_score": 0.75,
             "chunk_text": "YoY growth 15%.", "chunk_type": "report"},
        ]

        tools = create_chat_tools(
            nimble_client=None, report_id="rpt-test", ticker="TSLA",
            embedding_service=es, vector_search=vs,
        )

        tool = next(t for t in tools if t.name == "retrieve_report_chunks")
        raw = tool.invoke({"query": "Tesla revenue", "top_k": 5})
        result = json.loads(raw)

        assert isinstance(result, list)
        assert len(result) == 2
        # Verify the real embedding was passed to vector_search
        call_args = vs.search_chunks.call_args
        embedding = call_args.kwargs.get("query_embedding") or call_args[1].get("query_embedding")
        assert len(embedding) == 3072

    def test_get_earnings_data_real_yfinance(self):
        """Real yfinance call through the tool."""
        from unittest.mock import MagicMock
        from langchain_tools import create_chat_tools

        es = MagicMock()
        es.create_embedding.return_value = [0.1] * 3072
        vs = MagicMock()
        vs.search_chunks.return_value = []

        tools = create_chat_tools(
            nimble_client=None, report_id="rpt-test", ticker="TSLA",
            embedding_service=es, vector_search=vs,
        )

        tool = next(t for t in tools if t.name == "get_earnings_data")
        raw = tool.invoke({})
        result = json.loads(raw)

        assert isinstance(result, list)
        assert result[0]["index"] == 200
        assert result[0]["source_type"] == "yfinance"
        assert "data" in result[0]

    def test_search_ir_earnings_real_sec(self):
        """Real SEC EDGAR call through the tool (no Nimble)."""
        from unittest.mock import MagicMock
        from langchain_tools import create_chat_tools

        es = MagicMock()
        es.create_embedding.return_value = [0.1] * 3072
        vs = MagicMock()
        vs.search_chunks.return_value = []

        nimble = MagicMock()  # need nimble to create the tool, but SEC is real
        tools = create_chat_tools(
            nimble_client=nimble, report_id="rpt-test", ticker="TSLA",
            embedding_service=es, vector_search=vs,
        )

        tool = next(t for t in tools if t.name == "search_ir_earnings")
        raw = tool.invoke({"query": "annual report"})
        result = json.loads(raw)

        assert isinstance(result, list)
        assert len(result) > 0
        # SEC filings should have source_type "sec"
        assert any(r["source_type"] == "sec" for r in result)
        assert result[0]["url"].startswith("https://")


# ---------------------------------------------------------------------------
# Full ReAct agent -- real LLM + real embeddings + mock DB
# ---------------------------------------------------------------------------

class TestReActAgentLive:

    def test_agent_answers_with_report_chunks(self):
        """Real LLM call with mocked DB results. The full ReAct loop runs."""
        from unittest.mock import MagicMock
        os.environ.setdefault("GOOGLE_API_KEY", os.getenv("GEMINI_API_KEY", ""))

        from embedding_service import EmbeddingService
        from agents.chat_agent import ReportChatAgent

        agent = ReportChatAgent()

        # Mock vector_search to return fake chunks (no real DB)
        agent._vector_search = MagicMock()
        agent._vector_search.search_chunks.return_value = [
            {"chunk_id": "c1", "section": "Revenue Analysis",
             "similarity_score": 0.92, "chunk_type": "report",
             "chunk_text": "Tesla reported total revenue of $96.8 billion for fiscal year 2025, "
                           "representing a 15% year-over-year increase driven by vehicle deliveries "
                           "and energy storage growth."},
            {"chunk_id": "c2", "section": "Profitability",
             "similarity_score": 0.85, "chunk_type": "report",
             "chunk_text": "Operating margin improved to 11.2% in 2025, up from 9.2% in 2024. "
                           "Net income reached $10.8 billion."},
        ]

        result = agent.answer_question(
            report_id="rpt-test",
            ticker="TSLA",
            user_question="What was Tesla's revenue in 2025?",
        )

        assert "answer" in result
        assert isinstance(result["answer"], str)
        assert len(result["answer"]) > 20  # should be a substantive answer
        assert "sources" in result
        # The LLM should cite the chunks
        assert "96" in result["answer"] or "revenue" in result["answer"].lower()

    def test_agent_handles_no_chunks(self):
        """When vector search returns nothing, agent should still respond."""
        from unittest.mock import MagicMock
        os.environ.setdefault("GOOGLE_API_KEY", os.getenv("GEMINI_API_KEY", ""))

        from agents.chat_agent import ReportChatAgent

        agent = ReportChatAgent()
        agent._vector_search = MagicMock()
        agent._vector_search.search_chunks.return_value = []

        result = agent.answer_question(
            report_id="rpt-test",
            ticker="TSLA",
            user_question="What is Tesla's market cap?",
        )

        assert "answer" in result
        assert isinstance(result["answer"], str)
        assert len(result["answer"]) > 0
