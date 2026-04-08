"""
Cross-source verification tests: multiple source types cited together.
4 tests verifying citation filtering across report, SEC, and yfinance sources.
"""

import json
import re
from unittest.mock import patch, MagicMock

import pytest
from langchain_core.messages import AIMessage, ToolMessage


def _make_report_tool_msg(chunks):
    return ToolMessage(content=json.dumps(chunks), tool_call_id="tc-report", name="retrieve_report_chunks")


def _make_sec_tool_msg(items):
    return ToolMessage(content=json.dumps(items), tool_call_id="tc-sec", name="search_ir_earnings")


def _make_yf_tool_msg(data):
    return ToolMessage(content=json.dumps(data), tool_call_id="tc-yf", name="get_earnings_data")


def _make_agent():
    with patch("agents.chat_agent.EmbeddingService"), \
         patch("agents.chat_agent.VectorSearch"), \
         patch("agents.chat_agent.ChatGoogleGenerativeAI"):
        from agents.chat_agent import ReportChatAgent
        return ReportChatAgent()


REPORT_CHUNKS = [{"index": 1, "chunk_id": "c1", "section": "Revenue", "chunk_type": "report",
                   "similarity_score": 0.9, "chunk_text": "Revenue grew 20%."}]

SEC_ITEMS = [{"index": 100, "source_type": "sec", "title": "Tesla 10-K (2025-12-31)",
               "snippet": "Filed 2026-02-15", "url": "https://sec.gov/filing/10k"}]

YF_ITEMS = [{"index": 200, "source_type": "yfinance",
              "data": {"earnings_history": [{"index": "Q1 2025", "epsActual": 1.0, "epsEstimate": 0.9}],
                       "trailing_eps": 3.5, "forward_eps": 4.0}}]


def _simulate_answer(agent, answer_text, tool_messages):
    """Run _collect_sources + citation filtering logic."""
    all_sources = agent._collect_sources(tool_messages)
    cited_indices = {int(m) for m in re.findall(r'\[(\d+)\]', answer_text)}
    sources = [s for s in all_sources if s["index"] in cited_indices]
    if not sources and all_sources:
        sources = [s for s in all_sources if s["chunk_type"] in ("report", "research")]
    return sources


def test_report_and_yfinance_both_cited():
    agent = _make_agent()
    msgs = [_make_report_tool_msg(REPORT_CHUNKS), _make_yf_tool_msg(YF_ITEMS)]
    sources = _simulate_answer(agent, "Revenue grew [1]. EPS beat estimates [200].", msgs)

    types = {s["chunk_type"] for s in sources}
    assert "report" in types
    assert "yfinance" in types
    assert len(sources) == 2


def test_sec_and_report_both_cited():
    agent = _make_agent()
    msgs = [_make_report_tool_msg(REPORT_CHUNKS), _make_sec_tool_msg(SEC_ITEMS)]
    sources = _simulate_answer(agent, "Per the report [1], and the 10-K filing [100].", msgs)

    types = {s["chunk_type"] for s in sources}
    assert "report" in types
    assert "sec" in types


def test_all_three_source_types():
    agent = _make_agent()
    msgs = [_make_report_tool_msg(REPORT_CHUNKS), _make_sec_tool_msg(SEC_ITEMS), _make_yf_tool_msg(YF_ITEMS)]
    sources = _simulate_answer(agent, "Report [1], SEC [100], earnings [200].", msgs)

    types = {s["chunk_type"] for s in sources}
    assert types == {"report", "sec", "yfinance"}


def test_source_index_ranges_dont_collide():
    agent = _make_agent()
    report = [{"index": i, "chunk_id": f"c{i}", "section": "S", "chunk_type": "report",
                "similarity_score": 0.8, "chunk_text": "t"} for i in range(1, 8)]
    sec = [{"index": 100 + i, "source_type": "sec", "title": "F", "snippet": "s",
             "url": "https://sec.gov"} for i in range(3)]
    yf = [{"index": 200, "source_type": "yfinance", "data": {"earnings_history": []}}]

    msgs = [_make_report_tool_msg(report), _make_sec_tool_msg(sec), _make_yf_tool_msg(yf)]
    all_sources = agent._collect_sources(msgs)

    indices = [s["index"] for s in all_sources]
    # No duplicates
    assert len(indices) == len(set(indices))
    # Report in 1-7, SEC in 100-102, yfinance at 200
    report_idx = [i for i in indices if i < 100]
    sec_idx = [i for i in indices if 100 <= i < 200]
    yf_idx = [i for i in indices if i >= 200]
    assert len(report_idx) == 7
    assert len(sec_idx) == 3
    assert len(yf_idx) == 1
