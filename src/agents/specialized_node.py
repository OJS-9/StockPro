"""
SpecializedResearchAgent as a LangGraph node.

Uses LangGraph's create_react_agent to run a ReAct loop with MCP + Nimble tools.
Called in parallel for each research subject via the Send() API in research_graph.py.
"""

import logging
import os
from typing import Optional
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.prebuilt import create_react_agent
from langgraph.errors import GraphRecursionError

from research_subjects import ResearchSubject, get_research_subject_by_id
from date_utils import get_datetime_context_string
from retry_utils import is_rate_limit_error, run_with_exponential_backoff

logger = logging.getLogger(__name__)

SPECIALIZED_MODEL = os.getenv("SPECIALIZED_AGENT_MODEL", "gemini-2.5-pro")
SPECIALIZED_MAX_TURNS = int(os.getenv("SPECIALIZED_AGENT_MAX_TURNS", "8"))
SPECIALIZED_MAX_OUTPUT_TOKENS = int(
    os.getenv("SPECIALIZED_AGENT_MAX_OUTPUT_TOKENS", "6000")
)


_EMPTY_PHRASES = (
    "sorry, need more steps",
    "need more steps to process",
    "i need more steps",
)


def _extract_gathered_data(messages: list) -> str:
    """Dump all ToolMessage contents + reasoning AIMessages into a single blob."""
    parts = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            content = msg.content
            if isinstance(content, list):
                text = "\n".join(
                    (p.get("text", "") if isinstance(p, dict) else str(p))
                    for p in content
                )
            else:
                text = str(content) if content else ""
            if text.strip():
                parts.append(f"[Tool result] {text}")
        elif isinstance(msg, AIMessage):
            # Include prior reasoning text (not tool-call-only messages).
            content = msg.content
            if isinstance(content, list):
                text = "\n".join(
                    (p.get("text", "") if isinstance(p, dict) else str(p))
                    for p in content
                )
            else:
                text = str(content) if content else ""
            if text.strip():
                parts.append(f"[Analyst note] {text}")
    return "\n\n".join(parts)


def _rescue_finalize(
    llm,
    subject: ResearchSubject,
    ticker: str,
    trade_type: str,
    focus_hint: str,
    messages: list,
) -> tuple[str, int, int]:
    """Run a single no-tools LLM call to synthesize findings from gathered data.

    Returns (output_text, input_tokens, output_tokens).
    """
    gathered = _extract_gathered_data(messages)
    if not gathered.strip():
        return "", 0, 0

    focus_line = f"\nFocus: {focus_hint}\n" if focus_hint else ""
    rescue_prompt = (
        f"You are wrapping up research on {subject.name} for {ticker} ({trade_type}).{focus_line}\n"
        f"You already gathered the following data:\n\n{gathered}\n\n"
        "Write the final research output NOW using this data. This is your final response — "
        "do not call any more tools and do NOT say 'I need more steps'. "
        "Structure: **Key Findings**, **Supporting Data**, **Key Takeaways** "
        "(3-5 bullets with specific metrics). Quantify every claim."
    )
    try:
        resp = llm.invoke([HumanMessage(content=rescue_prompt)])
    except Exception as exc:
        logger.warning("%s: rescue finalize failed: %s", subject.id, exc)
        return "", 0, 0

    usage = getattr(resp, "usage_metadata", None) or {}
    in_tok = usage.get("input_tokens", 0)
    out_tok = usage.get("output_tokens", 0)

    content = resp.content
    if isinstance(content, list):
        text = "\n".join(
            (p.get("text", "") if isinstance(p, dict) else str(p)) for p in content
        )
    else:
        text = str(content) if content else ""
    return text, in_tok, out_tok


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
    subject: ResearchSubject,
    ticker: str,
    trade_type: str,
    focus_hint: str = "",
    effective_max_turns: int = SPECIALIZED_MAX_TURNS,
) -> str:
    datetime_context = get_datetime_context_string()
    focus_block = ""
    if focus_hint:
        focus_block = f"""
**Specific Research Focus (from user context):**
{focus_hint}
Prioritize this focus while still covering the full subject area.
"""
    qualitative_subjects = {
        "growth_drivers",
        "competitive_position",
        "sector_macro",
        "risk_factors",
        "management_quality",
    }
    subject_id_key = subject.id

    if subject_id_key in qualitative_subjects:
        tool_priority = (
            "1. perplexity_research — primary source for qualitative analysis, expert opinions, growth narratives\n"
            "2. nimble_web_search — fallback if Perplexity fails; search for analyst reports, news, industry trends\n"
            "3. yfinance_fundamentals or yfinance_analyst — if relevant financial context supports the subject"
        )
    elif subject_id_key == "news_catalysts":
        tool_priority = (
            "1. news_sentiment (Alpha Vantage) — primary source for recent news and sentiment scores\n"
            "2. perplexity_research — for upcoming catalysts, event calendars, recent developments\n"
            "3. nimble_web_search — fallback if both above fail"
        )
    elif subject_id_key == "technical_price_action":
        tool_priority = (
            "1. yfinance_options — options market data (IV, open interest, volume) for market sentiment\n"
            "2. perplexity_research — technical commentary, support/resistance levels\n"
            "3. nimble_web_search — fallback if Perplexity fails"
        )
    else:
        tool_priority = (
            "1. yfinance_fundamentals — primary source for all fundamental data (profile, financials, ratios, EPS)\n"
            "2. yfinance_analyst — analyst price targets, recommendations, upgrades/downgrades\n"
            "3. news_sentiment (Alpha Vantage) or perplexity_research — for context and recent developments"
        )

    return f"""You are a specialized research analyst focusing on {subject.name} for {ticker}.

{datetime_context}

Your specific research task: {subject.description}

**Research Objective:**
{subject.prompt_template.format(ticker=ticker)}
{focus_block}
**Trade Type:** {trade_type}

**Tool Priority (use in this order):**
{tool_priority}

**Fallback Rule:**
If a tool returns {{"status": "failed"}} or an error, immediately try the next tool in priority order.
Do NOT retry the same tool. Once you have data from at least one successful tool call, write your research output.

**Hard Turn Budget:**
You have at most {effective_max_turns} tool calls total for this subject. After your final tool call, you MUST write Key Findings / Supporting Data / Key Takeaways in the same response. Never say "I need more steps", "Sorry, need more steps", or any similar phrase — Gemini is penalized for this phrase and the run will be wasted. If you are near the turn limit, stop calling tools and write findings from the data you already have.

**Output:** Structure findings with Key Findings, Supporting Data, and Sources. Quantify every claim — no vague language. End with a **Key Takeaways** section (3-5 bullets, each with a specific metric or fact).

**IMPORTANT: You MUST call at least one tool before writing your response. Never rely on your training data — always fetch current data using the tools above.**"""


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
        instructions = _get_instructions(
            subject, ticker, trade_type, focus_hint, effective_max_turns
        )
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

        # Per-agent soft cost ceiling. Each subject gets a slice of the total
        # budget; parallel agents don't coordinate, so we allow 1.5x headroom.
        spend_budget_usd = state.get("spend_budget_usd")
        subject_count_state = state.get("effective_subject_count") or 1
        per_subject_ceiling_usd: Optional[float] = None
        if spend_budget_usd and spend_budget_usd > 0 and subject_count_state > 0:
            per_subject_ceiling_usd = (spend_budget_usd / subject_count_state) * 1.5

        def _run_specialized_once() -> dict:
            agent = create_react_agent(
                llm,
                tools,
                prompt=instructions,
            )
            # Stream so we can capture partial messages if recursion limit fires.
            collected_messages: list = []
            hit_recursion = False
            try:
                for step_state in agent.stream(
                    {"messages": [HumanMessage(content=research_prompt)]},
                    config={"recursion_limit": int(effective_max_turns) * 2},
                    stream_mode="values",
                ):
                    msgs = step_state.get("messages") if isinstance(step_state, dict) else None
                    if msgs:
                        collected_messages = list(msgs)
            except GraphRecursionError:
                hit_recursion = True
                logger.warning(
                    "%s: hit recursion limit after %s messages — rescuing",
                    subject_id,
                    len(collected_messages),
                )

            # Tally token usage from all collected messages.
            input_tok = 0
            output_tok = 0
            for msg in collected_messages:
                usage = getattr(msg, "usage_metadata", None) or {}
                input_tok += usage.get("input_tokens", 0)
                output_tok += usage.get("output_tokens", 0)

            # Extract last non-tool AI message as the normal research output.
            output_text = ""
            for msg in reversed(collected_messages):
                if (
                    isinstance(msg, AIMessage)
                    and msg.content
                    and not getattr(msg, "tool_calls", None)
                ):
                    content = msg.content
                    if isinstance(content, list):
                        output_text = "\n".join(
                            (
                                part.get("text", "")
                                if isinstance(part, dict)
                                else str(part)
                            )
                            for part in content
                        )
                    else:
                        output_text = str(content)
                    break

            empty_output = any(p in output_text.lower() for p in _EMPTY_PHRASES)
            needs_rescue = hit_recursion or empty_output or not output_text.strip()

            if needs_rescue and collected_messages:
                logger.warning(
                    "%s: rescuing output (recursion=%s, empty_phrase=%s, blank=%s)",
                    subject_id, hit_recursion, empty_output, not output_text.strip(),
                )
                rescued, r_in, r_out = _rescue_finalize(
                    llm, subject, ticker, trade_type, focus_hint, collected_messages
                )
                if rescued.strip():
                    output_text = rescued
                    input_tok += r_in
                    output_tok += r_out

            # Soft per-agent cost-ceiling logging (Part 2b).
            if per_subject_ceiling_usd is not None:
                try:
                    from spend_budget import get_gemini_usd_rates

                    rates = get_gemini_usd_rates()
                    if rates:
                        local_cost = (input_tok / 1000.0) * rates["input_rate"] + (
                            output_tok / 1000.0
                        ) * rates["output_rate"]
                        if local_cost > per_subject_ceiling_usd:
                            logger.info(
                                "%s: exceeded per-subject soft ceiling ($%.4f > $%.4f)",
                                subject_id, local_cost, per_subject_ceiling_usd,
                            )
                except Exception:
                    pass

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

        result = run_with_exponential_backoff(
            _run_specialized_once,
            max_retries=max_retries,
            base_delay_seconds=base_delay,
            is_retriable=is_rate_limit_error,
            log_label=subject_id,
        )
        if progress_fn := state.get("progress_fn"):
            progress_fn(None, f"Researched: {subject.name}")
        return result
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
                    "focus_hint": getattr(plan, "subject_focus", {}).get(
                        subject_id, ""
                    ),
                    "error": str(last_exc),
                }
            }
        }
