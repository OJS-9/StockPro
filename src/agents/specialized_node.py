"""
SpecializedResearchAgent as a LangGraph node.

Uses LangGraph's create_react_agent to run a ReAct loop with MCP + Nimble tools.
Called in parallel for each research subject via the Send() API in research_graph.py.
"""

import os
import time
from typing import Optional, Dict, Any

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

from research_subjects import ResearchSubject, get_research_subject_by_id
from date_utils import get_datetime_context_string

SPECIALIZED_MODEL = os.getenv("SPECIALIZED_AGENT_MODEL", "gemini-2.5-pro")
SPECIALIZED_MAX_TURNS = int(os.getenv("SPECIALIZED_AGENT_MAX_TURNS", "8"))
SPECIALIZED_MAX_OUTPUT_TOKENS = int(os.getenv("SPECIALIZED_AGENT_MAX_OUTPUT_TOKENS", "6000"))


def _get_clients():
    """Initialize MCP and Nimble clients (cached per-process via module-level singletons)."""
    from mcp_manager import MCPManager
    mcp_client = None
    nimble_client = None

    try:
        mcp_manager = MCPManager()
        mcp_client = mcp_manager.get_mcp_client()
    except Exception as e:
        print(f"[SpecializedNode] Warning: Could not initialize MCP client: {e}")

    try:
        from nimble_client import NimbleClient
        nimble_client = NimbleClient()
    except ValueError as e:
        print(f"[SpecializedNode] Info: Nimble not configured ({e}).")
    except Exception as e:
        print(f"[SpecializedNode] Warning: Could not initialize Nimble client: {e}")

    return mcp_client, nimble_client


def _get_instructions(subject: ResearchSubject, ticker: str, trade_type: str, focus_hint: str = "") -> str:
    datetime_context = get_datetime_context_string()
    focus_block = ""
    if focus_hint:
        focus_block = f"""
**Specific Research Focus (from user context):**
{focus_hint}
Prioritize this focus while still covering the full subject area.
"""
    return f"""You are a specialized research analyst focusing on {subject.name} for {ticker}.

{datetime_context}

Your specific research task: {subject.description}

**Research Objective:**
{subject.prompt_template.format(ticker=ticker)}
{focus_block}
**Trade Type Context:** {trade_type}
- Adjust your research depth and focus based on this trade type
- For Day Trade: Focus on immediate, actionable insights
- For Swing Trade: Focus on near-term factors (1-14 days)
- For Investment: Focus on comprehensive, long-term analysis

**Available Tools:**
- Alpha Vantage MCP Tools: Use for structured financial data, company fundamentals, financial statements
- Perplexity Research: Use for real-time information, news, expert analysis, qualitative insights

**Output Requirements:**
1. Provide comprehensive research findings on {subject.name}
2. Include specific data points, metrics, and facts
3. Cite all sources (tool outputs, research results)
4. Structure your response clearly with:
   - Key findings
   - Supporting data
   - Sources and citations
   - Any relevant context or analysis

Begin your research now."""


def _is_rate_limit_error(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status == 429:
        return True
    message = str(exc).lower()
    return "resource exhausted" in message or "rate limit" in message or "429" in message


def specialized_node(state: dict) -> dict:
    """
    LangGraph node: runs a ReAct agent for one research subject.

    Reads: ticker, trade_type, plan, subject_id, emitter
    Writes: research_outputs (merged via operator.or_ in ResearchState)
    """
    ticker = state["ticker"]
    trade_type = state["trade_type"]
    plan = state["plan"]
    subject_id = state["subject_id"]
    emitter = state.get("emitter")

    try:
        subject = get_research_subject_by_id(subject_id)
    except ValueError as exc:
        print(f"[SpecializedNode] Unknown subject '{subject_id}': {exc}")
        return {"research_outputs": {subject_id: {
            "subject_id": subject_id,
            "subject_name": subject_id,
            "research_output": f"Error: unknown subject id '{subject_id}'",
            "sources": [],
            "ticker": ticker,
            "trade_type": trade_type,
            "error": str(exc),
        }}}

    focus_hint = plan.subject_focus.get(subject_id, "")
    instructions = _get_instructions(subject, ticker, trade_type, focus_hint)
    research_prompt = subject.prompt_template.format(ticker=ticker)
    if focus_hint:
        research_prompt += f"\n\nSpecific focus for this analysis: {focus_hint}"

    mcp_client, nimble_client = _get_clients()

    from langchain_tools import create_all_tools
    tools = create_all_tools(mcp_client, nimble_client)

    llm = ChatGoogleGenerativeAI(
        model=SPECIALIZED_MODEL,
        temperature=0.7,
        max_output_tokens=SPECIALIZED_MAX_OUTPUT_TOKENS,
    )

    max_retries = int(os.getenv("AGENT_RATE_LIMIT_MAX_RETRIES", "3"))
    base_delay = float(os.getenv("AGENT_RATE_LIMIT_BACKOFF_SECONDS", "2.0"))
    last_exc: Optional[Exception] = None

    for attempt in range(max_retries):
        try:
            agent = create_react_agent(
                llm,
                tools,
                prompt=instructions,
            )
            result = agent.invoke(
                {"messages": [HumanMessage(content=research_prompt)]},
                config={"recursion_limit": SPECIALIZED_MAX_TURNS * 2},
            )
            # Extract the last AI message as the research output
            output_text = ""
            for msg in reversed(result["messages"]):
                if hasattr(msg, "content") and msg.content and not getattr(msg, "tool_calls", None):
                    output_text = msg.content
                    break

            print(f"[SpecializedNode] {subject.name}: {len(output_text)} chars")
            return {"research_outputs": {subject_id: {
                "subject_id": subject_id,
                "subject_name": subject.name,
                "research_output": output_text,
                "sources": [],
                "ticker": ticker,
                "trade_type": trade_type,
                "focus_hint": focus_hint,
            }}}

        except Exception as exc:
            last_exc = exc
            if not _is_rate_limit_error(exc) or attempt == max_retries - 1:
                break
            delay = base_delay * (2 ** attempt)
            print(f"[SpecializedNode:{subject_id}] Rate limit, retrying in {delay:.1f}s")
            time.sleep(delay)

    error_msg = f"Error in research for {subject.name}: {last_exc}"
    print(error_msg)
    return {"research_outputs": {subject_id: {
        "subject_id": subject_id,
        "subject_name": subject.name,
        "research_output": error_msg,
        "sources": [],
        "ticker": ticker,
        "trade_type": trade_type,
        "focus_hint": focus_hint,
        "error": str(last_exc),
    }}}
