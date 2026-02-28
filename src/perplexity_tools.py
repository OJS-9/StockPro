"""
Perplexity research tool execution.
"""

import os
from typing import Dict, Any

from perplexity_client import PerplexityClient

PERPLEXITY_TOOL_TIMEOUT_SECONDS = float(
    os.getenv("PERPLEXITY_TOOL_TIMEOUT_SECONDS", "10.0")
)

_FOCUS_PREFIXES = {
    "news": "Recent news and events: ",
    "analysis": "Expert analysis and opinions: ",
    "financial": "Financial market context: ",
    "general": "",
}

_SYSTEM_MESSAGES = {
    "news": "You are a financial news research assistant. Provide recent news, events, and developments with sources.",
    "analysis": "You are a financial analysis assistant. Provide expert opinions, market analysis, and insights with sources.",
    "financial": "You are a financial market research assistant. Provide financial context, market trends, and economic factors with sources.",
    "general": "You are a helpful research assistant that provides accurate, cited information.",
}


def execute_perplexity_research(
    perplexity_client: PerplexityClient,
    query: str,
    focus: str = "general",
) -> Dict[str, Any]:
    """
    Execute a Perplexity research query synchronously.

    Returns:
        Dict with keys: query, research, focus, status
    """
    prefix = _FOCUS_PREFIXES.get(focus, "")
    formatted_query = f"{prefix}{query}" if prefix else query
    system_message = _SYSTEM_MESSAGES.get(focus, _SYSTEM_MESSAGES["general"])

    try:
        research_content = perplexity_client.research(
            query=formatted_query,
            system_message=system_message,
            temperature=0.2,
            max_tokens=2000,
        )
        return {
            "query": query,
            "research": research_content,
            "focus": focus,
            "status": "success",
        }
    except Exception as e:
        return {
            "query": query,
            "research": f"Error performing research: {e}",
            "focus": focus,
            "status": "error",
            "error": str(e),
        }
