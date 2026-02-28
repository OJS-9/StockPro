"""
Google GenAI tool wrappers for MCP and Perplexity tools.
create_all_tools() returns (tools_list, handlers_dict) for use with gemini_runner.
"""

import json
from typing import Dict, Any, List, Optional, Tuple

from google.genai import types

from mcp_client import MCPClient
from mcp_tools import execute_tool_by_name
from perplexity_client import PerplexityClient
from perplexity_tools import execute_perplexity_research

MAX_SERIES_ITEMS = 5
MAX_NEWS_ITEMS = 5
MAX_RESEARCH_ITEMS = 3

# MCP tools exposed to specialized agents (matches research_prompt.py)
ESSENTIAL_MCP_TOOLS = {
    "OVERVIEW",
    "INCOME_STATEMENT",
    "BALANCE_SHEET",
    "CASH_FLOW",
    "EARNINGS",
    "NEWS_SENTIMENT",
}


def _json_schema_to_genai_schema(schema: Dict[str, Any]) -> types.Schema:
    """Convert a JSON Schema dict to a types.Schema for Gemini function declarations."""
    type_map = {
        "string": types.Type.STRING,
        "number": types.Type.NUMBER,
        "integer": types.Type.INTEGER,
        "boolean": types.Type.BOOLEAN,
        "array": types.Type.ARRAY,
        "object": types.Type.OBJECT,
    }

    schema_type = type_map.get(schema.get("type", "string"), types.Type.STRING)
    kwargs: Dict[str, Any] = {"type": schema_type}

    if "description" in schema:
        kwargs["description"] = schema["description"]

    if "enum" in schema:
        kwargs["enum"] = [str(v) for v in schema["enum"]]

    if "properties" in schema:
        kwargs["properties"] = {
            k: _json_schema_to_genai_schema(v)
            for k, v in schema["properties"].items()
        }

    if "required" in schema:
        kwargs["required"] = schema["required"]

    if "items" in schema:
        kwargs["items"] = _json_schema_to_genai_schema(schema["items"])

    return types.Schema(**kwargs)


def _make_mcp_handler(mcp_client: MCPClient, mcp_tool_name: str):
    """Return a sync handler callable for an MCP tool."""
    def handler(args: Dict[str, Any]) -> str:
        try:
            result = execute_tool_by_name(mcp_client, mcp_tool_name, args)
            if isinstance(result, dict):
                for key in ("annualReports", "quarterlyReports", "monthlyReports", "reports", "items", "data"):
                    if key in result and isinstance(result[key], list) and len(result[key]) > MAX_SERIES_ITEMS:
                        result[key] = result[key][:MAX_SERIES_ITEMS]
                if "feed" in result and isinstance(result["feed"], list) and len(result["feed"]) > MAX_NEWS_ITEMS:
                    result["feed"] = result["feed"][:MAX_NEWS_ITEMS]
                return json.dumps(result, indent=2, default=str)
            return str(result)
        except Exception as e:
            return json.dumps({"error": f"Tool execution failed: {e}", "tool": mcp_tool_name}, indent=2)
    return handler


def _make_perplexity_handler(perplexity_client: PerplexityClient):
    """Return a sync handler callable for the Perplexity research tool."""
    def handler(args: Dict[str, Any]) -> str:
        query = str(args.get("query", ""))
        focus = str(args.get("focus", "general"))
        if not query:
            return json.dumps({"error": "query parameter is required", "status": "error"})
        result = execute_perplexity_research(perplexity_client, query=query, focus=focus)
        if isinstance(result, dict):
            for key in ("results", "answers", "citations", "items"):
                if key in result and isinstance(result[key], list) and len(result[key]) > MAX_RESEARCH_ITEMS:
                    result[key] = result[key][:MAX_RESEARCH_ITEMS]
            return json.dumps(result, indent=2, default=str)
        return json.dumps({"research": str(result), "status": "success"})
    return handler


def create_mcp_tools(mcp_client: MCPClient) -> Tuple[List[types.Tool], Dict[str, Any]]:
    """Create Gemini Tool objects and handlers for the 6 essential MCP tools."""
    if not mcp_client:
        return [], {}

    all_tools = mcp_client.list_tools()
    tools_list: List[types.Tool] = []
    handlers: Dict[str, Any] = {}

    for tool in all_tools:
        mcp_tool_name = tool.get("name", "")
        if mcp_tool_name not in ESSENTIAL_MCP_TOOLS:
            continue

        description = tool.get("description", "")
        input_schema = tool.get("inputSchema", {})
        normalized_name = mcp_tool_name.lower().replace("-", "_")

        try:
            declaration = types.FunctionDeclaration(
                name=normalized_name,
                description=description,
                parameters=_json_schema_to_genai_schema(input_schema),
            )
            tools_list.append(types.Tool(function_declarations=[declaration]))
            handlers[normalized_name] = _make_mcp_handler(mcp_client, mcp_tool_name)
        except Exception as e:
            print(f"Warning: Could not create tool for {mcp_tool_name}: {e}")

    return tools_list, handlers


def create_perplexity_tool(perplexity_client: PerplexityClient) -> Tuple[Optional[types.Tool], Dict[str, Any]]:
    """Create Gemini Tool object and handler for Perplexity research."""
    if not perplexity_client:
        return None, {}

    parameters = types.Schema(
        type=types.Type.OBJECT,
        properties={
            "query": types.Schema(
                type=types.Type.STRING,
                description=(
                    "Research query or question to investigate. "
                    "Be specific and include context (e.g., company name, ticker symbol, time period)."
                ),
            ),
            "focus": types.Schema(
                type=types.Type.STRING,
                enum=["news", "analysis", "general", "financial"],
                description=(
                    "Focus area for the research. "
                    "'news' for recent news and events, "
                    "'analysis' for expert analysis and opinions, "
                    "'financial' for financial market context, "
                    "'general' for broad research (default)."
                ),
            ),
        },
        required=["query"],
    )

    declaration = types.FunctionDeclaration(
        name="perplexity_research",
        description=(
            "Perform real-time web research on a topic using Perplexity's Sonar API. "
            "Use this for finding recent news, market analysis, company developments, "
            "industry trends, and other information not available in structured financial data."
        ),
        parameters=parameters,
    )

    tool = types.Tool(function_declarations=[declaration])
    handler = _make_perplexity_handler(perplexity_client)
    return tool, {"perplexity_research": handler}


def create_all_tools(
    mcp_client: Optional[MCPClient],
    perplexity_client: Optional[PerplexityClient],
) -> Tuple[List[types.Tool], Dict[str, Any]]:
    """
    Create all tools for use with gemini_runner.

    Returns:
        (tools_list, handlers_dict) where tools_list is passed to the model
        and handlers_dict maps tool_name -> callable(args_dict) -> str
    """
    tools_list: List[types.Tool] = []
    handlers: Dict[str, Any] = {}

    if mcp_client:
        mcp_tools, mcp_handlers = create_mcp_tools(mcp_client)
        tools_list.extend(mcp_tools)
        handlers.update(mcp_handlers)

    if perplexity_client:
        perp_tool, perp_handlers = create_perplexity_tool(perplexity_client)
        if perp_tool:
            tools_list.append(perp_tool)
            handlers.update(perp_handlers)

    return tools_list, handlers
