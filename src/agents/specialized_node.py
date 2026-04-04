"""
SpecializedResearchAgent as a LangGraph node.

Uses LangGraph's create_react_agent to run a ReAct loop with MCP + Nimble tools.
Called in parallel for each research subject via the Send() API in research_graph.py.
"""

import logging
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

from research_subjects import ResearchSubject, get_research_subject_by_id
from date_utils import get_datetime_context_string
from retry_utils import is_rate_limit_error, run_with_exponential_backoff

logger = logging.getLogger(__name__)

SPECIALIZED_MODEL = os.getenv("SPECIALIZED_AGENT_MODEL", "gemini-2.5-pro")
SPECIALIZED_MAX_TURNS = int(os.getenv("SPECIALIZED_AGENT_MAX_TURNS", "8"))
SPECIALIZED_MAX_OUTPUT_TOKENS = int(
    os.getenv("SPECIALIZED_AGENT_MAX_OUTPUT_TOKENS", "6000")
)


def _get_clients():
    """Initialize MCP and Nimble clients (cached per-process via module-level singletons)."""
    from mcp_manager import MCPManager

    mcp_client = None
    nimble_client = None

    try:
        mcp_manager = MCPManager()
        mcp_client = mcp_manager.get_mcp_client()
    except Exception as e:
        logger.warning("Could not initialize MCP client: %s", e)

    try:
        from nimble_client import NimbleClient

        nimble_client = NimbleClient()
    except ValueError as e:
        logger.info("Nimble not configured (%s).", e)
    except Exception as e:
        logger.warning("Could not initialize Nimble client: %s", e)

    return mcp_client, nimble_client


def _get_instructions(
    subject: ResearchSubject, ticker: str, trade_type: str, focus_hint: str = ""
) -> str:
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
- yfinance_fundamentals: Company profile, valuation ratios, income statement, balance sheet, cash flow, EPS — use this first for all fundamental data
- yfinance_analyst: Analyst price targets, buy/sell/hold recommendations, upgrades/downgrades
- yfinance_ownership: Institutional holders, mutual fund holders, insider transactions
- yfinance_options: Options chain summary (open interest, IV, volume) — use for technical and risk subjects
- Alpha Vantage NEWS_SENTIMENT: News articles with sentiment scores — use for news and catalysts research
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


def specialized_node(state: dict) -> dict:
    """
    LangGraph node: runs a ReAct agent for one research subject.

    Reads: ticker, trade_type, plan, subject_id
    Writes: research_outputs (merged via operator.or_ in ResearchState)
    """
    ticker = state["ticker"]
    trade_type = state["trade_type"]
    plan = state["plan"]
    subject_id = state["subject_id"]
    effective_max_turns = state.get("effective_max_turns", SPECIALIZED_MAX_TURNS)
    effective_max_output_tokens = state.get(
        "effective_max_output_tokens", SPECIALIZED_MAX_OUTPUT_TOKENS
    )

    try:
        subject = get_research_subject_by_id(subject_id)
    except ValueError as exc:
        logger.error("Unknown subject '%s': %s", subject_id, exc)
        return {
            "research_outputs": {
                subject_id: {
                    "subject_id": subject_id,
                    "subject_name": subject_id,
                    "research_output": f"Error: unknown subject id '{subject_id}'",
                    "sources": [],
                    "ticker": ticker,
                    "trade_type": trade_type,
                    "error": str(exc),
                }
            }
        }

    try:
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
            max_output_tokens=effective_max_output_tokens,
        )

        max_retries = int(os.getenv("AGENT_RATE_LIMIT_MAX_RETRIES", "3"))
        base_delay = float(os.getenv("AGENT_RATE_LIMIT_BACKOFF_SECONDS", "2.0"))

        def _run_specialized_once() -> dict:
            agent = create_react_agent(
                llm,
                tools,
                prompt=instructions,
            )
            result = agent.invoke(
                {"messages": [HumanMessage(content=research_prompt)]},
                config={"recursion_limit": int(effective_max_turns) * 2},
            )
            # Extract the last AI message as the research output.
            # AIMessage.content can be str or list[dict] (multimodal format) in newer LangChain.
            output_text = ""
            input_tok = 0
            output_tok = 0
            for msg in result["messages"]:
                usage = getattr(msg, "usage_metadata", None) or {}
                input_tok += usage.get("input_tokens", 0)
                output_tok += usage.get("output_tokens", 0)

            for msg in reversed(result["messages"]):
                if (
                    isinstance(msg, AIMessage)
                    and msg.content
                    and not getattr(msg, "tool_calls", None)
                ):
                    content = msg.content
                    if isinstance(content, list):
                        output_text = "\n".join(
                            part.get("text", "") if isinstance(part, dict) else str(part)
                            for part in content
                        )
                    else:
                        output_text = str(content)
                    break

            logger.info(
                "%s: %s chars, %s/%s tokens",
                subject.name,
                len(output_text),
                input_tok,
                output_tok,
            )
            return {
                "research_outputs": {
                    subject_id: {
                        "subject_id": subject_id,
                        "subject_name": subject.name,
                        "research_output": output_text,
                        "sources": [],
                        "ticker": ticker,
                        "trade_type": trade_type,
                        "focus_hint": focus_hint,
                    }
                },
                "actual_input_tokens": input_tok,
                "actual_output_tokens": output_tok,
            }

        return run_with_exponential_backoff(
            _run_specialized_once,
            max_retries=max_retries,
            base_delay_seconds=base_delay,
            is_retriable=is_rate_limit_error,
            log_label=subject_id,
        )
    except Exception as last_exc:
        error_msg = f"Error in research for {subject.name}: {last_exc}"
        logger.error("%s", error_msg)
        return {
            "research_outputs": {
                subject_id: {
                    "subject_id": subject_id,
                    "subject_name": subject.name,
                    "research_output": error_msg,
                    "sources": [],
                    "ticker": ticker,
                    "trade_type": trade_type,
                    "focus_hint": getattr(plan, "subject_focus", {}).get(subject_id, ""),
                    "error": str(last_exc),
                }
            }
        }
