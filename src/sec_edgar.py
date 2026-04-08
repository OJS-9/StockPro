"""
SEC EDGAR client for fetching company filings via CIK lookup.
Free API, no key needed. Requires a User-Agent header per SEC policy.
"""

import logging
from typing import List, Dict, Any, Optional

import httpx

logger = logging.getLogger(__name__)

SEC_USER_AGENT = "StockPro Research support@stockpro.app"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_TIMEOUT = 10

# In-memory cache for ticker -> CIK mapping (loaded once, ~15KB)
_ticker_to_cik: Optional[Dict[str, int]] = None
_ticker_to_name: Optional[Dict[str, str]] = None


def _load_ticker_map() -> None:
    """Fetch and cache the SEC ticker -> CIK mapping."""
    global _ticker_to_cik, _ticker_to_name
    if _ticker_to_cik is not None:
        return

    headers = {"User-Agent": SEC_USER_AGENT, "Accept": "application/json"}
    try:
        with httpx.Client(timeout=SEC_TIMEOUT) as client:
            resp = client.get(SEC_TICKERS_URL, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        _ticker_to_cik = {}
        _ticker_to_name = {}
        for entry in data.values():
            sym = entry.get("ticker", "").upper()
            cik = entry.get("cik_str")
            title = entry.get("title", "")
            if sym and cik:
                _ticker_to_cik[sym] = int(cik)
                _ticker_to_name[sym] = title
    except Exception as e:
        logger.warning("Failed to load SEC ticker map: %s", e)
        _ticker_to_cik = {}
        _ticker_to_name = {}


def get_cik(ticker: str) -> Optional[int]:
    """Look up CIK for a ticker symbol."""
    _load_ticker_map()
    return (_ticker_to_cik or {}).get(ticker.upper())


def get_company_name(ticker: str) -> Optional[str]:
    """Look up SEC-registered company name for a ticker."""
    _load_ticker_map()
    return (_ticker_to_name or {}).get(ticker.upper())


def get_recent_filings(
    ticker: str,
    form_types: Optional[List[str]] = None,
    max_results: int = 5,
) -> List[Dict[str, Any]]:
    """
    Fetch recent SEC filings for a company by ticker.

    Args:
        ticker: Stock ticker symbol (e.g. AAPL, TSLA)
        form_types: Filter to specific form types (e.g. ["10-K", "10-Q", "8-K"]).
                    Defaults to ["10-K", "10-Q", "8-K"].
        max_results: Maximum number of filings to return.

    Returns:
        List of filing dicts with keys: form_type, filing_date, period,
        description, accession_number, url
    """
    if form_types is None:
        form_types = ["10-K", "10-Q", "8-K"]

    cik = get_cik(ticker)
    if cik is None:
        logger.warning("No CIK found for ticker %s", ticker)
        return []

    # Pad CIK to 10 digits as required by SEC API
    cik_padded = str(cik).zfill(10)
    url = SEC_SUBMISSIONS_URL.format(cik=cik_padded)
    headers = {"User-Agent": SEC_USER_AGENT, "Accept": "application/json"}

    try:
        with httpx.Client(timeout=SEC_TIMEOUT) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("SEC EDGAR submissions fetch failed for %s: %s", ticker, e)
        return []

    # Extract recent filings from the submissions data
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    descriptions = recent.get("primaryDocDescription", [])
    periods = recent.get("reportDate", [])

    form_types_set = {ft.upper() for ft in form_types}
    results = []

    for i in range(len(forms)):
        if forms[i].upper() not in form_types_set:
            continue

        accession = accessions[i].replace("-", "") if i < len(accessions) else ""
        accession_dashed = accessions[i] if i < len(accessions) else ""
        primary_doc = primary_docs[i] if i < len(primary_docs) else ""

        # Build direct URL to the filing document
        filing_url = ""
        if accession and primary_doc:
            filing_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{primary_doc}"

        company_name = get_company_name(ticker) or ticker
        filing_date = dates[i] if i < len(dates) else ""
        period = periods[i] if i < len(periods) else ""
        description = descriptions[i] if i < len(descriptions) else ""

        results.append({
            "form_type": forms[i],
            "filing_date": filing_date,
            "period": period,
            "description": description or f"{company_name} {forms[i]}",
            "accession_number": accession_dashed,
            "url": filing_url,
            "company_name": company_name,
        })

        if len(results) >= max_results:
            break

    return results
