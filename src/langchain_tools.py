"""
LangChain tool wrappers for MCP (Alpha Vantage) and Nimble tools.
create_all_tools() returns List[StructuredTool] for use with LangGraph agents.
"""

import json
import logging
import math
from typing import Dict, Any, List, Optional

from langchain_core.tools import StructuredTool

from mcp_client import MCPClient
from mcp_tools import execute_tool_by_name
from nimble_client import NimbleClient

logger = logging.getLogger(__name__)


def _sanitize_nan(obj):
    """Recursively replace NaN/Inf floats with None so json.dumps produces valid JSON."""
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_nan(v) for v in obj]
    return obj


MAX_SERIES_ITEMS = 5
MAX_NEWS_ITEMS = 5

ESSENTIAL_MCP_TOOLS = {
    "NEWS_SENTIMENT",
}


def _make_mcp_handler(mcp_client: MCPClient, mcp_tool_name: str):
    def handler(**kwargs: Any) -> str:
        try:
            result = execute_tool_by_name(mcp_client, mcp_tool_name, kwargs)
            if isinstance(result, dict):
                for key in (
                    "annualReports",
                    "quarterlyReports",
                    "monthlyReports",
                    "reports",
                    "items",
                    "data",
                ):
                    if (
                        key in result
                        and isinstance(result[key], list)
                        and len(result[key]) > MAX_SERIES_ITEMS
                    ):
                        result[key] = result[key][:MAX_SERIES_ITEMS]
                if (
                    "feed" in result
                    and isinstance(result["feed"], list)
                    and len(result["feed"]) > MAX_NEWS_ITEMS
                ):
                    result["feed"] = result["feed"][:MAX_NEWS_ITEMS]
                return json.dumps(result, indent=2, default=str)
            return str(result)
        except Exception as e:
            return json.dumps(
                {
                    "error": f"Tool execution failed: {e}",
                    "tool": mcp_tool_name,
                    "suggestion": "Try a yfinance tool or nimble_web_search as an alternative data source.",
                },
                indent=2,
            )

    return handler


def create_mcp_tools(mcp_client: MCPClient) -> List[StructuredTool]:
    """Create LangChain StructuredTools for the 6 essential Alpha Vantage MCP tools."""
    if not mcp_client:
        return []

    all_tools = mcp_client.list_tools()
    tools: List[StructuredTool] = []

    for tool_def in all_tools:
        mcp_tool_name = tool_def.get("name", "")
        if mcp_tool_name not in ESSENTIAL_MCP_TOOLS:
            continue

        description = tool_def.get("description", "")
        input_schema = tool_def.get("inputSchema", {})
        normalized_name = mcp_tool_name.lower().replace("-", "_")
        handler = _make_mcp_handler(mcp_client, mcp_tool_name)

        # Build args_schema from inputSchema properties
        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])

        # Create a dynamic pydantic model for the schema
        from pydantic import Field, create_model

        field_defs: Dict[str, Any] = {}
        for prop_name, prop_schema in properties.items():
            prop_desc = prop_schema.get("description", "")
            if prop_name in required:
                field_defs[prop_name] = (str, Field(description=prop_desc))
            else:
                field_defs[prop_name] = (
                    Optional[str],
                    Field(default=None, description=prop_desc),
                )

        ArgsModel = create_model(f"{normalized_name}_args", **field_defs)

        try:
            structured_tool = StructuredTool.from_function(
                func=handler,
                name=normalized_name,
                description=description,
                args_schema=ArgsModel,
            )
            tools.append(structured_tool)
        except Exception as e:
            logger.warning("Could not create tool for %s: %s", mcp_tool_name, e)

    return tools


def create_nimble_tools(nimble_client: NimbleClient) -> List[StructuredTool]:
    """Create LangChain StructuredTools for Nimble web search, extract, and Perplexity."""
    if not nimble_client:
        return []

    from pydantic import BaseModel, Field
    from typing import Literal

    # --- nimble_web_search ---
    class NimbleSearchArgs(BaseModel):
        query: str = Field(
            description="Search query. Include company name, ticker, and topic."
        )
        num_results: int = Field(
            default=5, description="Number of results (default 5, max 10)."
        )
        topic: Literal["general", "news", "shopping", "social"] = Field(
            default="general",
            description="Search topic filter. Use 'news' for recent news.",
        )
        time_range: Optional[Literal["hour", "day", "week", "month", "year"]] = Field(
            default=None, description="Limit results by time period. Optional."
        )
        deep_search: bool = Field(
            default=False,
            description=(
                "If true, fetches full page content for each result (slower, 15-45s). "
                "Reduce num_results to 3 or fewer when enabling."
            ),
        )

    def nimble_web_search(
        query: str,
        num_results: int = 5,
        topic: str = "general",
        time_range: Optional[str] = None,
        deep_search: bool = False,
    ) -> str:
        try:
            result = nimble_client.search(
                query,
                num_results=num_results,
                topic=topic,
                time_range=time_range,
                deep_search=deep_search,
            )
            return json.dumps(result, indent=2, default=str)
        except Exception as e:
            return json.dumps({
                "error": f"Nimble search failed: {e}",
                "suggestion": "Try perplexity_research for a synthesized answer, or yfinance tools for financial data.",
            })

    # --- nimble_extract ---
    class NimbleExtractArgs(BaseModel):
        url: str = Field(description="Full URL of the page to extract content from.")
        render: bool = Field(
            default=False, description="Enable JS rendering for dynamic pages."
        )

    MAX_EXTRACT_CHARS = 10000

    def nimble_extract(url: str, render: bool = False) -> str:
        try:
            result = nimble_client.extract(url, render=render)
            text = json.dumps(result, indent=2, default=str)
            if len(text) > MAX_EXTRACT_CHARS:
                return text[:MAX_EXTRACT_CHARS] + (
                    "\n\n[Content truncated at 10,000 characters. "
                    "Use nimble_web_search for a summary instead.]"
                )
            return text
        except Exception as e:
            return json.dumps({
                "error": f"Nimble extract failed: {e}",
                "suggestion": "Check the URL is valid. Try nimble_web_search to find an alternative source.",
            })

    # --- perplexity_research ---
    class PerplexityArgs(BaseModel):
        query: str = Field(
            description="Research query. Be specific — include company name, ticker, time period."
        )
        focus: Literal["news", "analysis", "general", "financial"] = Field(
            default="general",
            description=(
                "'news' for recent events, 'analysis' for expert opinions, "
                "'financial' for market context, 'general' for broad research."
            ),
        )

    def perplexity_research(query: str, focus: str = "general") -> str:
        try:
            result = nimble_client.perplexity_research(query, focus)
            if isinstance(result, str) and result.startswith("[Nimble Perplexity"):
                return json.dumps(
                    {
                        "status": "failed",
                        "error": result,
                        "suggestion": "Try nimble_web_search or a yfinance tool instead.",
                    }
                )
            return json.dumps({"research": result, "status": "success"})
        except Exception as e:
            return json.dumps({
                "status": "failed",
                "error": f"perplexity_research failed: {e}",
                "suggestion": "Try nimble_web_search for a direct web search, or yfinance tools for financial data.",
            })

    return [
        StructuredTool.from_function(
            func=nimble_web_search,
            name="nimble_web_search",
            description=(
                "Search the web for specific facts: news articles, press releases, analyst reports, "
                "SEC filings, financial data, company announcements. Returns raw search results "
                "you must analyze yourself. Use this for any factual lookup."
            ),
            args_schema=NimbleSearchArgs,
        ),
        StructuredTool.from_function(
            func=nimble_extract,
            name="nimble_extract",
            description=(
                "Extract and parse full page content from a specific URL. "
                "Use when you have a URL from search results that you need to read in full "
                "(e.g., a press release, earnings transcript, SEC filing page)."
            ),
            args_schema=NimbleExtractArgs,
        ),
        StructuredTool.from_function(
            func=perplexity_research,
            name="perplexity_research",
            description=(
                "Get a synthesized analytical answer to a complex research question. "
                "Use ONLY when you need expert-level synthesis across multiple sources — "
                "e.g. 'What is the consensus view on X competitive moat?' "
                "Do NOT use for simple fact-finding (use nimble_web_search instead)."
            ),
            args_schema=PerplexityArgs,
        ),
    ]


def _df_to_records(df, max_rows: int = 4, transpose: bool = True) -> list:
    """
    Convert a yfinance DataFrame to a JSON-serializable list of records.
    Financial statement DFs have metrics as rows and dates as columns — transpose=True
    flips them so each record is one time period. Use transpose=False when dates are
    already the index (e.g. earnings_history, recommendations).
    """
    try:
        if df is None or df.empty:
            return []
        out = df.T.reset_index() if transpose else df.reset_index()
        records = out.head(max_rows).to_dict(orient="records")
        # JSON keys must be strings; Timestamps from column names are not.
        return [{str(k): v for k, v in row.items()} for row in records]
    except Exception:
        return []


def create_yfinance_tools() -> List[StructuredTool]:
    """Create LangChain StructuredTools backed by yfinance."""
    from pydantic import BaseModel, Field

    class SymbolArgs(BaseModel):
        symbol: str = Field(description="Stock ticker symbol, e.g. AAPL, MSFT.")

    # --- yfinance_fundamentals ---
    def yfinance_fundamentals(symbol: str) -> str:
        """
        Fetch company fundamentals from Yahoo Finance: profile, income statement,
        balance sheet, cash flow, and earnings (EPS actuals vs estimates).
        Replaces Alpha Vantage OVERVIEW + INCOME_STATEMENT + BALANCE_SHEET + CASH_FLOW + EARNINGS.
        """
        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            info = ticker.info or {}

            profile = {
                k: info.get(k)
                for k in (
                    "symbol",
                    "longName",
                    "longBusinessSummary",
                    "sector",
                    "industry",
                    "country",
                    "fullTimeEmployees",
                    "website",
                    "marketCap",
                    "enterpriseValue",
                    "trailingPE",
                    "forwardPE",
                    "priceToBook",
                    "priceToSalesTrailing12Months",
                    "enterpriseToRevenue",
                    "enterpriseToEbitda",
                    "totalRevenue",
                    "revenueGrowth",
                    "grossMargins",
                    "operatingMargins",
                    "profitMargins",
                    "ebitda",
                    "netIncomeToCommon",
                    "earningsGrowth",
                    "earningsQuarterlyGrowth",
                    "totalCash",
                    "totalDebt",
                    "debtToEquity",
                    "currentRatio",
                    "trailingEps",
                    "forwardEps",
                    "bookValue",
                    "dividendRate",
                    "dividendYield",
                    "payoutRatio",
                    "beta",
                    "52WeekChange",
                    "targetHighPrice",
                    "targetLowPrice",
                    "targetMeanPrice",
                    "recommendationKey",
                    "numberOfAnalystOpinions",
                )
            }

            result = {
                "profile": profile,
                "annual_income_statement": _df_to_records(ticker.income_stmt),
                "quarterly_income_statement": _df_to_records(
                    ticker.quarterly_income_stmt
                ),
                "annual_balance_sheet": _df_to_records(ticker.balance_sheet),
                "quarterly_balance_sheet": _df_to_records(
                    ticker.quarterly_balance_sheet
                ),
                "annual_cash_flow": _df_to_records(ticker.cash_flow),
                "quarterly_cash_flow": _df_to_records(ticker.quarterly_cash_flow),
                "earnings_history": _df_to_records(
                    ticker.earnings_history, max_rows=8, transpose=False
                ),
            }
            return json.dumps(_sanitize_nan(result), indent=2, default=str)
        except Exception as e:
            return json.dumps({
                "error": f"yfinance_fundamentals failed for {symbol}: {e}",
                "suggestion": "Try yfinance_analyst for a lighter data pull, or nimble_web_search to find fundamentals online.",
            })

    # --- yfinance_analyst ---
    def yfinance_analyst(symbol: str) -> str:
        """
        Fetch analyst data from Yahoo Finance: price targets, buy/sell/hold recommendations,
        and recent upgrades/downgrades. Useful for valuation and company overview research.
        """
        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            result = {
                "price_targets": _df_to_records(
                    ticker.analyst_price_targets, max_rows=10, transpose=False
                ),
                "recommendations": _df_to_records(
                    ticker.recommendations, max_rows=10, transpose=False
                ),
                "upgrades_downgrades": _df_to_records(
                    ticker.upgrades_downgrades, max_rows=10, transpose=False
                ),
                "next_earnings_date": str(
                    ticker.calendar.get("Earnings Date", [None])[0]
                    if ticker.calendar
                    else None
                ),
            }
            return json.dumps(_sanitize_nan(result), indent=2, default=str)
        except Exception as e:
            return json.dumps({
                "error": f"yfinance_analyst failed for {symbol}: {e}",
                "suggestion": "Try yfinance_fundamentals for broader data, or nimble_web_search for analyst coverage.",
            })

    # --- yfinance_ownership ---
    def yfinance_ownership(symbol: str) -> str:
        """
        Fetch ownership data from Yahoo Finance: top institutional holders,
        mutual fund holders, and recent insider transactions (buys/sells).
        Useful for competitive position, risk factors, and management quality research.
        """
        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            result = {
                "institutional_holders": _df_to_records(
                    ticker.institutional_holders, max_rows=10, transpose=False
                ),
                "mutualfund_holders": _df_to_records(
                    ticker.mutualfund_holders, max_rows=10, transpose=False
                ),
                "insider_transactions": _df_to_records(
                    ticker.insider_transactions, max_rows=10, transpose=False
                ),
            }
            return json.dumps(_sanitize_nan(result), indent=2, default=str)
        except Exception as e:
            return json.dumps({
                "error": f"yfinance_ownership failed for {symbol}: {e}",
                "suggestion": "Try nimble_web_search for institutional holder data, or sec_edgar_filings for insider filings.",
            })

    # --- yfinance_options ---
    def yfinance_options(symbol: str) -> str:
        """
        Fetch options market data from Yahoo Finance: available expiration dates
        and a summary of the nearest expiry's calls and puts (open interest,
        implied volatility, volume). Useful for technical analysis and risk research.
        """
        try:
            import yfinance as yf

            ticker = yf.Ticker(symbol)
            expirations = ticker.options
            if not expirations:
                return json.dumps(
                    {"error": "No options data available", "symbol": symbol}
                )

            nearest = expirations[0]
            chain = ticker.option_chain(nearest)
            calls = _df_to_records(
                chain.calls[
                    [
                        "strike",
                        "lastPrice",
                        "openInterest",
                        "impliedVolatility",
                        "volume",
                    ]
                ],
                max_rows=8,
            )
            puts = _df_to_records(
                chain.puts[
                    [
                        "strike",
                        "lastPrice",
                        "openInterest",
                        "impliedVolatility",
                        "volume",
                    ]
                ],
                max_rows=8,
            )
            result = {
                "expiration_dates": list(expirations[:6]),
                "nearest_expiry": nearest,
                "calls": calls,
                "puts": puts,
            }
            return json.dumps(_sanitize_nan(result), indent=2, default=str)
        except Exception as e:
            return json.dumps({
                "error": f"yfinance_options failed for {symbol}: {e}",
                "suggestion": "Try nimble_web_search for options market data or perplexity_research for technical analysis.",
            })

    return [
        StructuredTool.from_function(
            func=yfinance_fundamentals,
            name="yfinance_fundamentals",
            description=(
                "Fetch company fundamentals from Yahoo Finance: business profile, valuation ratios, "
                "annual and quarterly income statement, balance sheet, cash flow, and EPS earnings. "
                "Use this instead of Alpha Vantage OVERVIEW / INCOME_STATEMENT / BALANCE_SHEET / "
                "CASH_FLOW / EARNINGS — same data, no rate limits."
            ),
            args_schema=SymbolArgs,
        ),
        StructuredTool.from_function(
            func=yfinance_analyst,
            name="yfinance_analyst",
            description=(
                "Fetch analyst consensus data from Yahoo Finance: price targets (high/low/mean), "
                "buy/sell/hold recommendation history, and recent rating upgrades/downgrades. "
                "Use for valuation, company overview, and investment research subjects."
            ),
            args_schema=SymbolArgs,
        ),
        StructuredTool.from_function(
            func=yfinance_ownership,
            name="yfinance_ownership",
            description=(
                "Fetch ownership data from Yahoo Finance: top institutional and mutual fund holders "
                "(name, % held, shares), and recent insider transactions (buys/sells with dollar amounts). "
                "Use for competitive position, risk factors, and management quality research."
            ),
            args_schema=SymbolArgs,
        ),
        StructuredTool.from_function(
            func=yfinance_options,
            name="yfinance_options",
            description=(
                "Fetch options market data from Yahoo Finance: expiration dates, and calls/puts summary "
                "(strike, open interest, implied volatility, volume) for the nearest expiry. "
                "Use for technical/price action and risk factor research — especially day trade and swing trade."
            ),
            args_schema=SymbolArgs,
        ),
    ]


def create_sec_edgar_tool() -> StructuredTool:
    """Create a StructuredTool for searching SEC EDGAR filings by ticker."""
    from pydantic import BaseModel, Field
    from typing import Literal

    class SECEdgarArgs(BaseModel):
        symbol: str = Field(description="Stock ticker symbol, e.g. AAPL, TSLA, MSFT.")
        form_types: str = Field(
            default="10-K,10-Q,8-K",
            description=(
                "Comma-separated SEC form types to search. "
                "Common types: 10-K (annual report), 10-Q (quarterly report), "
                "8-K (current report/earnings). Default: '10-K,10-Q,8-K'."
            ),
        )
        max_results: int = Field(
            default=5, description="Maximum number of filings to return (default 5)."
        )

    def sec_edgar_filings(symbol: str, form_types: str = "10-K,10-Q,8-K", max_results: int = 5) -> str:
        """Fetch recent SEC filings for a company using CIK lookup."""
        try:
            from sec_edgar import get_recent_filings

            types_list = [ft.strip() for ft in form_types.split(",") if ft.strip()]
            filings = get_recent_filings(symbol, form_types=types_list, max_results=max_results)

            if not filings:
                return json.dumps({"message": f"No SEC filings found for {symbol}", "results": []})

            results = []
            for f in filings:
                results.append({
                    "form_type": f["form_type"],
                    "filing_date": f["filing_date"],
                    "period": f["period"],
                    "description": f["description"],
                    "url": f["url"],
                    "company": f.get("company_name", symbol),
                })
            return json.dumps(results, indent=2, default=str)
        except Exception as e:
            return json.dumps({
                "error": f"SEC EDGAR lookup failed: {e}",
                "suggestion": "Try nimble_web_search for SEC filings, or yfinance_fundamentals for financial statement data.",
            })

    return StructuredTool.from_function(
        func=sec_edgar_filings,
        name="sec_edgar_filings",
        description=(
            "Search SEC EDGAR for official company filings by ticker symbol. "
            "Returns recent 10-K (annual), 10-Q (quarterly), and 8-K (current/earnings) reports "
            "with direct links to the filing documents. Use for earnings data, financial statements, "
            "and official company disclosures."
        ),
        args_schema=SECEdgarArgs,
    )


def create_all_tools(
    mcp_client: Optional[MCPClient],
    nimble_client: Optional[NimbleClient] = None,
) -> List[StructuredTool]:
    """
    Create all LangChain tools for specialized research agents.

    Returns:
        List of StructuredTool objects ready for use with create_react_agent.
    """
    tools: List[StructuredTool] = []

    tools.extend(create_yfinance_tools())

    if mcp_client:
        tools.extend(create_mcp_tools(mcp_client))

    if nimble_client:
        tools.extend(create_nimble_tools(nimble_client))

    tools.append(create_sec_edgar_tool())

    return tools


def create_chat_tools(
    nimble_client,
    report_id: str,
    ticker: str,
    embedding_service,
    vector_search,
    progress_fn=None,
) -> List[StructuredTool]:
    """Create tools for the report chat ReAct agent."""
    from pydantic import BaseModel, Field

    FALLBACK_THRESHOLD = 0.45

    class RetrieveArgs(BaseModel):
        query: str = Field(description="Search query to find relevant report sections.")
        top_k: int = Field(default=5, description="Number of chunks to retrieve.")

    def retrieve_report_chunks(query: str, top_k: int = 5) -> str:
        if progress_fn:
            progress_fn("Searching report...")
        try:
            query_embedding = embedding_service.create_embedding(query)
            report_chunks = vector_search.search_chunks(
                report_id=report_id,
                query_embedding=query_embedding,
                top_k=top_k,
                chunk_type="report",
            )
            best_score = report_chunks[0]["similarity_score"] if report_chunks else 0.0
            if best_score < FALLBACK_THRESHOLD or len(report_chunks) < 2:
                research_chunks = vector_search.search_chunks(
                    report_id=report_id,
                    query_embedding=query_embedding,
                    top_k=3,
                    chunk_type="research",
                )
                all_chunks = report_chunks + research_chunks
            else:
                all_chunks = report_chunks
            seen = set()
            results = []
            for c in sorted(all_chunks, key=lambda x: x["similarity_score"], reverse=True):
                if c["chunk_id"] not in seen:
                    seen.add(c["chunk_id"])
                    results.append({
                        "index": len(results) + 1,
                        "chunk_id": c["chunk_id"],
                        "section": c.get("section"),
                        "chunk_type": c.get("chunk_type", "report"),
                        "similarity_score": round(c["similarity_score"], 4),
                        "chunk_text": c["chunk_text"],
                    })
            results = results[:top_k + 2]
            return json.dumps(results, indent=2, default=str)
        except Exception as e:
            return json.dumps({"error": f"Report chunk retrieval failed: {e}"})

    class IRSearchArgs(BaseModel):
        query: str = Field(
            description="Specific earnings/IR topic, e.g. 'Q1 2026 earnings results', 'revenue guidance', 'earnings call transcript'. Do NOT include the ticker or company name -- those are added automatically."
        )

    def search_ir_earnings(query: str) -> str:
        if progress_fn:
            progress_fn("Searching SEC filings...")
        try:
            import re as _re
            from sec_edgar import get_recent_filings, get_company_name

            # Phase 1: SEC EDGAR via CIK lookup (most reliable)
            sec_filings = get_recent_filings(ticker, form_types=["10-K", "10-Q", "8-K"], max_results=5)
            sec_results = []
            for f in sec_filings:
                sec_results.append({
                    "source_type": "sec",
                    "title": f"{f['company_name']} - {f['form_type']} ({f['period'] or f['filing_date']})",
                    "snippet": f"Filed {f['filing_date']}. Period: {f['period']}. {f['description']}",
                    "url": f["url"],
                    "file_type": f["form_type"],
                })

            # Phase 2: If SEC returned < 2, fall back to Nimble web search
            nimble_results = []
            if len(sec_results) < 2 and nimble_client:
                if progress_fn:
                    progress_fn("Searching investor relations news...")

                company_name = get_company_name(ticker) or ticker
                clean_name = _re.sub(r'[\s,]*(Inc\.?|Corp\.?|Ltd\.?|LLC|PLC|Co\.?|Group|Holdings?)[\s,]*$', '', company_name, flags=_re.IGNORECASE).strip().rstrip(',')
                ticker_lower = ticker.lower()
                name_lower = clean_name.lower()

                search_query = f'"{clean_name}" ({ticker}) {query} earnings OR "investor relations" OR "quarterly results" OR 10-K OR 10-Q'
                result = nimble_client.search(search_query, num_results=10, topic="general", time_range="month")

                for r in result.get("results", []):
                    title = (r.get("title", "") or "").lower()
                    snippet = (r.get("snippet", "") or r.get("description", "") or "").lower()
                    text = title + " " + snippet
                    if ticker_lower in text or name_lower in text:
                        nimble_results.append({
                            "source_type": "ir",
                            "title": r.get("title", ""),
                            "snippet": r.get("snippet", r.get("description", "")),
                            "url": r.get("url", r.get("link", "")),
                        })
                    if len(nimble_results) >= 3:
                        break

            # Merge: SEC filings first, then Nimble
            all_results = sec_results + nimble_results

            # Return indexed (100+ range)
            indexed = []
            for i, r in enumerate(all_results[:5], start=100):
                indexed.append({
                    "index": i,
                    "source_type": r.get("source_type", "ir"),
                    "title": r.get("title", ""),
                    "snippet": r.get("snippet", ""),
                    "url": r.get("url", ""),
                    "file_type": r.get("file_type"),
                })
            return json.dumps(indexed, indent=2, default=str)
        except Exception as e:
            return json.dumps({"error": f"IR search failed: {e}"})

    def get_earnings_data() -> str:
        if progress_fn:
            progress_fn("Pulling earnings data...")
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            info = t.info or {}
            data = {
                "earnings_history": _df_to_records(t.earnings_history, max_rows=8, transpose=False),
                "next_earnings_date": str(
                    t.calendar.get("Earnings Date", [None])[0] if t.calendar else None
                ),
                "earnings_growth": info.get("earningsGrowth"),
                "earnings_quarterly_growth": info.get("earningsQuarterlyGrowth"),
                "trailing_eps": info.get("trailingEps"),
                "forward_eps": info.get("forwardEps"),
            }
            # Wrap in indexed format so agent can cite by number (200+ range)
            result = [{
                "index": 200,
                "source_type": "yfinance",
                "data": _sanitize_nan(data),
            }]
            return json.dumps(result, indent=2, default=str)
        except Exception as e:
            return json.dumps({"error": f"Earnings data failed: {e}"})

    tools = [
        StructuredTool.from_function(
            func=retrieve_report_chunks,
            name="retrieve_report_chunks",
            description=(
                "Search the stored research report for relevant sections. "
                "ALWAYS call this first to ground your answer in the report. "
                "Returns numbered chunks with section names and text."
            ),
            args_schema=RetrieveArgs,
        ),
        StructuredTool.from_function(
            func=get_earnings_data,
            name="get_earnings_data",
            description=(
                "Pull structured earnings data from Yahoo Finance: EPS history (actual vs estimates), "
                "next earnings date, growth rates. Use for specific numerical comparisons."
            ),
        ),
    ]

    if nimble_client:
        tools.append(
            StructuredTool.from_function(
                func=search_ir_earnings,
                name="search_ir_earnings",
                description=(
                    "Search SEC EDGAR filings (10-K, 10-Q, 8-K) and investor relations news "
                    "for the company's official earnings, guidance, and financial announcements. "
                    "The ticker and company name are added automatically -- only pass the topic "
                    "(e.g. 'Q1 2026 earnings', 'annual report', 'revenue guidance'). "
                    "Use when the question involves earnings, revenue, guidance, or financial results."
                ),
                args_schema=IRSearchArgs,
            )
        )

    return tools
