"""
LangChain tool wrappers for MCP (Alpha Vantage) and Nimble tools.
create_all_tools() returns List[StructuredTool] for use with LangGraph agents.
"""

import json
import logging
from typing import Dict, Any, List, Optional

from langchain_core.tools import StructuredTool

from mcp_client import MCPClient
from mcp_tools import execute_tool_by_name
from nimble_client import NimbleClient

logger = logging.getLogger(__name__)

MAX_SERIES_ITEMS = 5
MAX_NEWS_ITEMS = 5

ESSENTIAL_MCP_TOOLS = {
    "OVERVIEW",
    "INCOME_STATEMENT",
    "BALANCE_SHEET",
    "CASH_FLOW",
    "EARNINGS",
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
        result = nimble_client.perplexity_research(query, focus)
        return json.dumps({"research": result, "status": "success"})

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

    if mcp_client:
        tools.extend(create_mcp_tools(mcp_client))

    if nimble_client:
        tools.extend(create_nimble_tools(nimble_client))

    return tools
