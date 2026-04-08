"""
Tests for create_sec_edgar_tool() and its presence in create_all_tools().
3 tests with mocked SEC EDGAR calls.
"""

import json
from unittest.mock import patch, MagicMock

import pytest


@patch("sec_edgar.get_recent_filings")
def test_sec_tool_returns_filings_json(mock_filings):
    mock_filings.return_value = [
        {
            "form_type": "10-K",
            "filing_date": "2026-02-15",
            "period": "2025-12-31",
            "description": "Annual Report",
            "url": "https://sec.gov/filing/10k",
            "company_name": "Tesla, Inc",
            "accession_number": "0001-26-000001",
        },
    ]
    from langchain_tools import create_sec_edgar_tool
    tool = create_sec_edgar_tool()
    raw = tool.invoke({"symbol": "TSLA"})
    result = json.loads(raw)

    assert isinstance(result, list)
    assert result[0]["form_type"] == "10-K"
    assert result[0]["url"].startswith("https://")


@patch("sec_edgar.get_recent_filings")
def test_sec_tool_no_filings(mock_filings):
    mock_filings.return_value = []
    from langchain_tools import create_sec_edgar_tool
    tool = create_sec_edgar_tool()
    raw = tool.invoke({"symbol": "ZZZZZ"})
    result = json.loads(raw)

    assert result["message"].startswith("No SEC filings found")
    assert result["results"] == []


def test_sec_tool_in_create_all_tools():
    with patch("langchain_tools.create_yfinance_tools", return_value=[]), \
         patch("langchain_tools.create_mcp_tools", return_value=[]), \
         patch("langchain_tools.create_nimble_tools", return_value=[]):
        from langchain_tools import create_all_tools
        tools = create_all_tools(mcp_client=None, nimble_client=None)
        names = [t.name for t in tools]
        assert "sec_edgar_filings" in names
