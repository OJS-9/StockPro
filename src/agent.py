"""
Stock Research Agent — orchestrates conversation, clarifying questions,
and triggers report generation via the Gemini runner.
"""

import os
import json
import re
import time
import uuid
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

from google import genai
from google.genai import types

from src.research_prompt import get_orchestration_instructions
from src.research_orchestrator import ResearchOrchestrator
from src.synthesis_agent import SynthesisAgent
from src.report_storage import ReportStorage
from src.report_chat_agent import ReportChatAgent
from src.planner_agent import PlannerAgent
from src.research_plan import ResearchPlan
from src.gemini_runner import run_agent, _get_client
from src.trace_service import TraceContext

load_dotenv()

ORCHESTRATOR_MODEL = os.getenv("ORCHESTRATOR_MODEL", "gemini-3-flash-preview")
ORCHESTRATOR_MAX_OUTPUT_TOKENS = int(os.getenv("ORCHESTRATOR_MAX_OUTPUT_TOKENS", "600"))
ORCHESTRATOR_MAX_TURNS = int(os.getenv("ORCHESTRATOR_MAX_TURNS", "6"))
ORCHESTRATOR_MAX_HISTORY_MESSAGES = int(os.getenv("ORCHESTRATOR_MAX_HISTORY_MESSAGES", "4"))
ORCHESTRATOR_MAX_MESSAGE_CHARS = int(os.getenv("ORCHESTRATOR_MAX_MESSAGE_CHARS", "1000"))
ORCHESTRATOR_DEBUG_TOKEN_LOG = os.getenv("ORCHESTRATOR_DEBUG_TOKEN_LOG", "false").lower() == "true"


class StockResearchAgent:
    """Stock research agent using Google Gemini with tool-based orchestration."""

    def __init__(self, api_key: Optional[str] = None):
        # api_key kept for interface compatibility; Gemini key comes from env
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.conversation_history: List[Dict[str, str]] = []
        self.current_ticker: Optional[str] = None
        self.current_trade_type: Optional[str] = None
        self.current_report_id: Optional[str] = None
        self.last_report_text: Optional[str] = None
        self.current_plan: Optional[ResearchPlan] = None
        self.user_id = None
        self._trace_context: Optional[TraceContext] = None
        self.research_orchestrator = ResearchOrchestrator(api_key=self.api_key)
        self.synthesis_agent = SynthesisAgent(api_key=self.api_key)
        self.planner_agent = PlannerAgent(api_key=self.api_key)
        self.report_storage = ReportStorage()
        self.chat_agent = ReportChatAgent()

        # Build the generate_report tool declaration and handler
        self._generate_report_tool = self._make_generate_report_tool()
        self._tool_handlers = {"generate_report": self._generate_report_handler}

    def _make_generate_report_tool(self) -> types.Tool:
        declaration = types.FunctionDeclaration(
            name="generate_report",
            description=(
                "Trigger report generation when you have gathered enough information from the user. "
                "Use this tool when you have asked 1-2 relevant questions and the user has provided sufficient context. "
                "This will activate specialized research agents to perform comprehensive analysis and generate the final report. "
                "Only call this tool when you are ready to proceed — don't call it immediately after asking questions."
            ),
            parameters=types.Schema(type=types.Type.OBJECT, properties={}, required=[]),
        )
        return types.Tool(function_declarations=[declaration])

    def _generate_report_handler(self, args: Dict[str, Any]) -> str:
        """Handler called when the orchestrator invokes the generate_report tool."""
        try:
            context_str = "\n".join(
                f"User: {msg['content']}"
                for msg in self.conversation_history
                if msg.get("role") == "user"
            )
            self.generate_report(context=context_str)
            report_id = self.current_report_id or ""
            return (
                f"Report generated successfully! Report ID: {report_id[:8]}...\n\n"
                "The comprehensive research report has been created and is ready to view."
            )
        except Exception as e:
            return f"Error generating report: {e}"

    def start_research(self, ticker: str, trade_type: str) -> str:
        """Start a research session for a given ticker and trade type."""
        self.current_ticker = ticker.upper()
        self.current_trade_type = trade_type

        system_instructions = get_orchestration_instructions(ticker, trade_type)
        user_message = f"I want to research {ticker} for a {trade_type} strategy. Please help me create a fundamental research report."

        self.conversation_history = [
            {"role": "system", "content": system_instructions},
            {"role": "user", "content": user_message},
        ]

        return self._get_agent_response(user_message, system_instructions)

    def continue_conversation(self, user_response: str) -> str:
        """Continue the conversation with a user response."""
        self.conversation_history.append({"role": "user", "content": user_response})

        system_instructions = next(
            (msg["content"] for msg in self.conversation_history if msg["role"] == "system"),
            "",
        )

        return self._get_agent_response(user_response, system_instructions)

    def _get_agent_response(self, user_message: str, system_instructions: str) -> str:
        """Run the orchestration agent for one conversational turn."""
        try:
            # Build contents from recent conversation history (exclude system messages)
            recent = self.conversation_history[-ORCHESTRATOR_MAX_HISTORY_MESSAGES:]
            contents: List[types.Content] = []

            for msg in recent:
                if msg["role"] == "system":
                    continue
                content = msg["content"]
                if isinstance(content, str) and len(content) > ORCHESTRATOR_MAX_MESSAGE_CHARS:
                    content = content[:ORCHESTRATOR_MAX_MESSAGE_CHARS] + "... [truncated]"
                role = "model" if msg["role"] == "assistant" else "user"
                contents.append(
                    types.Content(role=role, parts=[types.Part.from_text(text=content)])
                )

            # Ensure current user message is the last entry (append if missing or different)
            current_content = user_message
            if isinstance(current_content, str) and len(current_content) > ORCHESTRATOR_MAX_MESSAGE_CHARS:
                current_content = current_content[:ORCHESTRATOR_MAX_MESSAGE_CHARS] + "... [truncated]"
            last_is_current_user = (
                contents
                and contents[-1].role == "user"
                and contents[-1].parts
                and getattr(contents[-1].parts[0], "text", None) == current_content
            )
            if not last_is_current_user:
                contents.append(
                    types.Content(role="user", parts=[types.Part.from_text(text=current_content)])
                )

            if ORCHESTRATOR_DEBUG_TOKEN_LOG:
                print(f"[Orchestrator] Approx input chars: {len(str(contents))}, history_messages={len(recent)}")

            assistant_message = _run_agent_with_retry(
                model=ORCHESTRATOR_MODEL,
                system_instruction=system_instructions,
                tools=[self._generate_report_tool],
                tool_handlers=self._tool_handlers,
                contents=contents,
                max_turns=ORCHESTRATOR_MAX_TURNS,
                temperature=0.7,
                max_output_tokens=ORCHESTRATOR_MAX_OUTPUT_TOKENS,
                trace_context=self._trace_context,
                parent_span=None,
            )

            if ORCHESTRATOR_DEBUG_TOKEN_LOG:
                print(f"[Orchestrator] Approx output chars: {len(str(assistant_message))}")

            self.conversation_history.append({"role": "assistant", "content": assistant_message})
            return assistant_message

        except Exception as e:
            error_msg = f"Error generating response: {e}"
            print(f"Agent execution error: {e}")
            return error_msg

    def generate_report(self, context: str = "") -> str:
        """Generate a research report using parallel agents."""
        if not self.current_ticker or not self.current_trade_type:
            return "Error: No active research session. Please start research first."

        ticker = self.current_ticker
        trade_type = self.current_trade_type

        print(f"\n{'='*60}")
        print(f"Starting parallel research for {ticker} ({trade_type})")
        print(f"{'='*60}\n")

        tc = self._trace_context
        print(f"[TRACE DEBUG] _trace_context={tc}, _root_span={getattr(tc, '_root_span', 'N/A')}, _lf={getattr(tc, '_lf', 'N/A')}")

        try:
            print(f"{'='*60}")
            print("Building research plan with PlannerAgent...")
            print(f"{'='*60}\n")

            if tc:
                tc.emit_step("Planning research subjects...")
            plan = self.planner_agent.build_plan(
                ticker=ticker,
                trade_type=trade_type,
                conversation_context=context,
                trace_context=tc,
            )
            self.current_plan = plan

            subject_names = ", ".join(plan.selected_subject_ids)
            print(
                f"Research plan: {len(plan.selected_subject_ids)} subjects — "
                + subject_names
            )
            if tc:
                tc.emit_step(f"Researching: {subject_names}...")

            research_outputs = self.research_orchestrator.run_parallel_research(
                plan=plan, trace_context=tc
            )

            print(f"\n{'='*60}")
            print("Synthesizing research findings into final report...")
            print(f"{'='*60}\n")

            if tc:
                tc.emit_step("Synthesizing report...")
            synthesis_span = tc.start_span("synthesis", input=ticker) if tc else None
            report_text = self.synthesis_agent.synthesize_report(
                ticker=ticker,
                trade_type=trade_type,
                research_outputs=research_outputs,
                plan=plan,
                trace_context=tc,
                parent_span=synthesis_span,
            )
            if tc:
                tc.end_span(synthesis_span, output=f"{len(report_text)} chars")

            self.last_report_text = report_text
            self.current_report_id = str(uuid.uuid4())

            print(f"\n{'='*60}")
            print("Storing report with chunking and embeddings...")
            print(f"{'='*60}\n")

            if tc:
                tc.emit_step("Storing report...")
            metadata = {
                "trade_type": trade_type,
                "research_subjects": plan.selected_subject_ids,
                "trade_context": plan.trade_context,
                "planner_reasoning": plan.planner_reasoning,
            }

            storage_span = tc.start_span("storage", input=ticker) if tc else None
            try:
                report_id = self.report_storage.store_report(
                    ticker=ticker,
                    trade_type=trade_type,
                    report_text=report_text,
                    metadata=metadata,
                    user_id=self.user_id,
                )
                self.current_report_id = report_id
                if tc:
                    tc.end_span(storage_span, output=report_id)
                print(f"\n{'='*60}")
                print(f"Report generated and stored: {report_id}")
                print(f"{'='*60}\n")
            except Exception as storage_err:
                if tc:
                    tc.end_span(storage_span, error=str(storage_err))
                print(f"Report storage failed (display will still work, RAG chat disabled): {storage_err}")

            return report_text

        except Exception as e:
            error_msg = f"Error generating report: {e}"
            print(error_msg)
            return error_msg
        finally:
            print(f"[TRACE DEBUG] finally block reached, tc={tc}")
            if tc:
                tc.finish(output=f"Report {self.current_report_id or 'unknown'}")
                print(f"[TRACE DEBUG] tc.finish() called")

    def chat_with_report(self, question: str) -> str:
        """Chat with the current report using RAG-lite."""
        if not self.current_report_id:
            return "Error: No report available. Please generate a report first."
        return self.chat_agent.chat_with_report(
            report_id=self.current_report_id,
            question=question,
        )

    def set_trace_context(self, tc: Optional[TraceContext]):
        """Attach a TraceContext for step emission and LangFuse spans."""
        self._trace_context = tc

    def reset_conversation(self):
        """Reset the conversation history."""
        self.conversation_history = []
        self.current_ticker = None
        self.current_trade_type = None
        self.current_report_id = None
        self.current_plan = None
        self.chat_agent.reset_conversation()


def _is_rate_limit_error(exc: Exception) -> bool:
    """Heuristic check for Gemini rate limit errors."""
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status == 429:
        return True
    message = str(exc).lower()
    return "resource exhausted" in message or "rate limit" in message or "429" in message


def _run_agent_with_retry(
    model: str,
    system_instruction: str,
    tools: list,
    tool_handlers: dict,
    contents: list,
    max_turns: int,
    temperature: float,
    max_output_tokens: int,
    trace_context=None,
    parent_span=None,
) -> str:
    max_retries = int(os.getenv("AGENT_RATE_LIMIT_MAX_RETRIES", "3"))
    base_delay = float(os.getenv("AGENT_RATE_LIMIT_BACKOFF_SECONDS", "2.0"))
    last_exc: Optional[Exception] = None

    for attempt in range(max_retries):
        try:
            return run_agent(
                model=model,
                system_instruction=system_instruction,
                tools=tools,
                tool_handlers=tool_handlers,
                messages=contents,
                max_turns=max_turns,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                thinking_budget=0,
                trace_context=trace_context,
                parent_span=parent_span,
            )
        except Exception as exc:
            last_exc = exc
            if not _is_rate_limit_error(exc) or attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            print(
                f"[Orchestrator] Rate limit encountered, retrying in {delay:.1f}s "
                f"(attempt {attempt + 1}/{max_retries})"
            )
            time.sleep(delay)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Unknown error in _run_agent_with_retry")


def create_agent(api_key: Optional[str] = None) -> StockResearchAgent:
    return StockResearchAgent(api_key=api_key)
