"""
Tests for src/sec_edgar.py -- CIK lookup, company name, and filings retrieval.
6 tests with mocked HTTP calls.
"""

import json
from unittest.mock import patch, MagicMock

import pytest


# Sample SEC ticker map response
MOCK_TICKER_MAP = {
    "0": {"cik_str": 1318605, "ticker": "TSLA", "title": "Tesla, Inc"},
    "1": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
}

# Sample SEC submissions response
MOCK_SUBMISSIONS = {
    "cik": "1318605",
    "name": "Tesla, Inc",
    "filings": {
        "recent": {
            "form": ["10-K", "10-Q", "8-K", "4", "10-Q", "8-K"],
            "filingDate": ["2026-02-15", "2025-11-01", "2025-10-20", "2025-09-01", "2025-08-01", "2025-07-15"],
            "accessionNumber": [
                "0001-26-000001", "0001-25-000002", "0001-25-000003",
                "0001-25-000004", "0001-25-000005", "0001-25-000006",
            ],
            "primaryDocument": ["doc1.htm", "doc2.htm", "doc3.htm", "doc4.htm", "doc5.htm", "doc6.htm"],
            "primaryDocDescription": ["Annual Report", "Quarterly", "Current Report", "", "Quarterly", "Current"],
            "reportDate": ["2025-12-31", "2025-09-30", "", "", "2025-06-30", ""],
        }
    },
}


def _mock_httpx_get(url, **kwargs):
    """Return appropriate mock response based on URL."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    if "company_tickers" in url:
        resp.json.return_value = MOCK_TICKER_MAP
    elif "submissions" in url:
        resp.json.return_value = MOCK_SUBMISSIONS
    return resp


@pytest.fixture(autouse=True)
def reset_ticker_cache():
    """Reset the module-level cache before each test."""
    import sec_edgar
    sec_edgar._ticker_to_cik = None
    sec_edgar._ticker_to_name = None
    yield
    sec_edgar._ticker_to_cik = None
    sec_edgar._ticker_to_name = None


@pytest.fixture
def mock_http():
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.get.side_effect = _mock_httpx_get
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client
        yield mock_client


def test_get_cik_known_ticker(mock_http):
    from sec_edgar import get_cik
    cik = get_cik("TSLA")
    assert cik == 1318605


def test_get_cik_unknown_ticker(mock_http):
    from sec_edgar import get_cik
    cik = get_cik("ZZZZZ")
    assert cik is None


def test_get_company_name(mock_http):
    from sec_edgar import get_company_name
    name = get_company_name("TSLA")
    assert name == "Tesla, Inc"


def test_get_recent_filings_filters_form_types(mock_http):
    from sec_edgar import get_recent_filings
    filings = get_recent_filings("TSLA", form_types=["10-K"], max_results=10)
    assert all(f["form_type"] == "10-K" for f in filings)
    assert len(filings) == 1  # only one 10-K in mock data


def test_get_recent_filings_max_results(mock_http):
    from sec_edgar import get_recent_filings
    filings = get_recent_filings("TSLA", form_types=["10-K", "10-Q", "8-K"], max_results=2)
    assert len(filings) <= 2


def test_get_recent_filings_unknown_ticker(mock_http):
    from sec_edgar import get_recent_filings
    filings = get_recent_filings("ZZZZZ", form_types=["10-K"])
    assert filings == []
