"""
Specialized research agents for focused research on specific business model aspects.
"""

import os
import time
from typing import Optional, Dict, Any
from dotenv import load_dotenv

from google.genai import types

from src.gemini_runner import run_agent
from src.mcp_manager import MCPManager
from src.agent_tools import create_all_tools
from src.research_subjects import ResearchSubject

load_dotenv()

SPECIALIZED_AGENT_MODEL = os.getenv("SPECIALIZED_AGENT_MODEL", "gemini-3.1-pro-preview")
SPECIALIZED_AGENT_MAX_TURNS = int(os.getenv("SPECIALIZED_AGENT_MAX_TURNS", "8"))
SPECIALIZED_AGENT_MAX_OUTPUT_TOKENS = int(os.getenv("SPECIALIZED_AGENT_MAX_OUTPUT_TOKENS", "6000"))
SPECIALIZED_AGENT_DEBUG_TOKEN_LOG = os.getenv("SPECIALIZED_AGENT_DEBUG_TOKEN_LOG", "false").lower() == "true"


class SpecializedResearchAgent:
    """Specialized agent for researching a specific business model aspect."""

    def __init__(self, api_key: Optional[str] = None):
        # api_key kept for interface compatibility; Gemini key comes from env
        self.mcp_manager = MCPManager()
        self.mcp_client = None
        self.perplexity_client = None
        self.tools_list = []
        self.tool_handlers = {}

        self._initialize_clients()
        self._initialize_tools()

    def _initialize_clients(self):
        try:
            self.mcp_client = self.mcp_manager.get_mcp_client()
        except Exception as e:
            print(f"Warning: Could not initialize MCP client: {e}")
            self.mcp_client = None

        try:
            from perplexity_client import PerplexityClient
            self.perplexity_client = PerplexityClient()
        except ValueError as e:
            print(f"Info: Perplexity API not configured ({e}). Continuing with Alpha Vantage tools only.")
            self.perplexity_client = None
        except Exception as e:
            print(f"Warning: Could not initialize Perplexity client: {e}")
            self.perplexity_client = None

    def _initialize_tools(self):
        try:
            self.tools_list, self.tool_handlers = create_all_tools(self.mcp_client, self.perplexity_client)
        except Exception as e:
            print(f"Warning: Could not create tools: {e}")
            self.tools_list = []
            self.tool_handlers = {}

    def get_specialized_instructions(
        self,
        subject: ResearchSubject,
        ticker: str,
        trade_type: str,
        focus_hint: str = "",
    ) -> str:
        from src.date_utils import get_datetime_context_string

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

**Important:**
- Use both MCP tools and Perplexity research to gather comprehensive information
- Be thorough and specific in your research
- Ensure all claims are supported by data from your research tools
- Format your response for easy integration into a final report

Begin your research now."""

    def _build_research_prompt(
        self,
        subject: ResearchSubject,
        ticker: str,
        trade_type: str,
        focus_hint: str = "",
    ) -> str:
        base_prompt = subject.prompt_template.format(ticker=ticker)
        if focus_hint:
            base_prompt += f"\n\nSpecific focus for this analysis: {focus_hint}"
        return base_prompt

    def research_subject(
        self,
        ticker: str,
        subject: ResearchSubject,
        trade_type: str,
        focus_hint: str = "",
    ) -> Dict[str, Any]:
        """Research a specific subject for a ticker."""
        instructions = self.get_specialized_instructions(subject, ticker, trade_type, focus_hint)
        research_prompt = self._build_research_prompt(subject, ticker, trade_type, focus_hint)

        if SPECIALIZED_AGENT_DEBUG_TOKEN_LOG:
            print(f"[SpecializedAgent:{subject.id}] Approx input chars: {len(research_prompt)}")

        try:
            research_output = _run_specialized_agent_with_retry(
                model=SPECIALIZED_AGENT_MODEL,
                system_instruction=instructions,
                tools_list=self.tools_list,
                tool_handlers=self.tool_handlers,
                research_prompt=research_prompt,
                max_turns=SPECIALIZED_AGENT_MAX_TURNS,
            )

            if SPECIALIZED_AGENT_DEBUG_TOKEN_LOG:
                print(f"[SpecializedAgent:{subject.id}] Approx output chars: {len(str(research_output))}")

            return {
                "subject_id": subject.id,
                "subject_name": subject.name,
                "research_output": research_output,
                "sources": [],
                "ticker": ticker,
                "trade_type": trade_type,
                "focus_hint": focus_hint,
            }

        except Exception as e:
            error_msg = f"Error in specialized research for {subject.name}: {e}"
            print(error_msg)
            return {
                "subject_id": subject.id,
                "subject_name": subject.name,
                "research_output": error_msg,
                "sources": [],
                "ticker": ticker,
                "trade_type": trade_type,
                "focus_hint": focus_hint,
                "error": str(e),
            }


def _is_rate_limit_error(exc: Exception) -> bool:
    """Heuristic check for Gemini rate limit errors."""
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status == 429:
        return True
    message = str(exc).lower()
    return "resource exhausted" in message or "rate limit" in message or "429" in message


def _run_specialized_agent_with_retry(
    model: str,
    system_instruction: str,
    tools_list: list,
    tool_handlers: dict,
    research_prompt: str,
    max_turns: int,
) -> str:
    max_retries = int(os.getenv("AGENT_RATE_LIMIT_MAX_RETRIES", "3"))
    base_delay = float(os.getenv("AGENT_RATE_LIMIT_BACKOFF_SECONDS", "2.0"))
    last_exc: Optional[Exception] = None

    messages = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=research_prompt)],
        )
    ]

    for attempt in range(max_retries):
        try:
            return run_agent(
                model=model,
                system_instruction=system_instruction,
                tools=tools_list,
                tool_handlers=tool_handlers,
                messages=messages,
                max_turns=max_turns,
                temperature=0.7,
                max_output_tokens=SPECIALIZED_AGENT_MAX_OUTPUT_TOKENS,
            )
        except Exception as exc:
            last_exc = exc
            if not _is_rate_limit_error(exc) or attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            print(
                f"[SpecializedAgent] Rate limit encountered, retrying in {delay:.1f}s "
                f"(attempt {attempt + 1}/{max_retries})"
            )
            time.sleep(delay)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Unknown error in _run_specialized_agent_with_retry")
