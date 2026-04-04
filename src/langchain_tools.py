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
                {"error": f"Tool execution failed: {e}", "tool": mcp_tool_name},
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
            return json.dumps({"error": f"Nimble search failed: {e}"})

    # --- nimble_extract ---
    class NimbleExtractArgs(BaseModel):
        url: str = Field(description="Full URL of the page to extract content from.")
        render: bool = Field(
            default=False, description="Enable JS rendering for dynamic pages."
        )

    def nimble_extract(url: str, render: bool = False) -> str:
        try:
            result = nimble_client.extract(url, render=render)
            return json.dumps(result, indent=2, default=str)
        except Exception as e:
            return json.dumps({"error": f"Nimble extract failed: {e}"})

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
            return json.dumps(
                {"status": "failed", "error": f"perplexity_research failed: {e}"}
            )

    return [
        StructuredTool.from_function(
            func=nimble_web_search,
            name="nimble_web_search",
            description=(
                "Search the web in real-time using Nimble's infrastructure. "
                "Use for recent news, analyst reports, company announcements, industry trends."
            ),
            args_schema=NimbleSearchArgs,
        ),
        StructuredTool.from_function(
            func=nimble_extract,
            name="nimble_extract",
            description=(
                "Extract and parse content from a specific URL using Nimble's browser infrastructure. "
                "Use for press releases, SEC filings, earnings transcripts, IR pages."
            ),
            args_schema=NimbleExtractArgs,
        ),
        StructuredTool.from_function(
            func=perplexity_research,
            name="perplexity_research",
            description=(
                "Perform real-time web research using Perplexity (via Nimble). "
                "Use for recent news, market analysis, company developments, industry trends."
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
            return json.dumps(
                {"error": f"yfinance_fundamentals failed for {symbol}: {e}"}
            )

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
            return json.dumps({"error": f"yfinance_analyst failed for {symbol}: {e}"})

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
            return json.dumps({"error": f"yfinance_ownership failed for {symbol}: {e}"})

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
            return json.dumps({"error": f"yfinance_options failed for {symbol}: {e}"})

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

    return tools
