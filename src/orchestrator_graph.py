"""
Conversational orchestrator as a LangGraph ReAct agent.

Replaces StockResearchAgent (agent.py). Manages the conversation with the user,
asks clarifying questions, and triggers the research pipeline via the
generate_report tool when ready.
"""

import logging
import os
from typing import Optional, List, Dict, Any

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import create_react_agent

from research_prompt import get_orchestration_instructions
from research_graph import run_research
from agents.chat_agent import ReportChatAgent
from langsmith_service import StepEmitter

logger = logging.getLogger(__name__)

ORCHESTRATOR_MODEL = os.getenv("ORCHESTRATOR_MODEL", "gemini-2.5-flash")
ORCHESTRATOR_MAX_OUTPUT_TOKENS = int(os.getenv("ORCHESTRATOR_MAX_OUTPUT_TOKENS", "600"))


class OrchestratorSession:
    """
    Manages a single user research session.
    Wraps the LangGraph orchestrator agent and holds session state.
    """

    def __init__(self, user_id: Optional[int] = None):
        self.user_id = user_id
        self.username: Optional[str] = None
        self.current_ticker: Optional[str] = None
        self.current_trade_type: Optional[str] = None
        self.current_report_id: Optional[str] = None
        self.last_report_text: Optional[str] = None
        self.pending_questions: List[Dict[str, Any]] = []
        self.conversation_history: List[Dict[str, str]] = []
        self._chat_agent = ReportChatAgent()
        self._emitter: Optional[StepEmitter] = None

    def set_emitter(self, emitter: Optional[StepEmitter]):
        self._emitter = emitter

    def start_research(self, ticker: str, trade_type: str) -> str:
        """Start a new research session."""
        self.current_ticker = ticker.upper()
        self.current_trade_type = trade_type
        self.conversation_history = []

        system_instructions = get_orchestration_instructions(ticker, trade_type)
        user_message = (
            f"I want to research {ticker} for a {trade_type} strategy. "
            "Please help me create a fundamental research report."
        )
        self.conversation_history.append(
            {"role": "system", "content": system_instructions}
        )
        self.conversation_history.append({"role": "user", "content": user_message})

        return self._get_agent_response(user_message, system_instructions)

    def continue_conversation(self, user_response: str) -> str:
        """Continue with a user response."""
        self.conversation_history.append({"role": "user", "content": user_response})
        system_instructions = next(
            (m["content"] for m in self.conversation_history if m["role"] == "system"),
            "",
        )
        return self._get_agent_response(user_response, system_instructions)

    def _get_agent_response(self, user_message: str, system_instructions: str) -> str:
        """Run one turn of the orchestrator ReAct agent."""
        ticker = self.current_ticker or ""
        trade_type = self.current_trade_type or ""
        session = self

        @tool
        def ask_user_questions(questions: List[Dict[str, Any]]) -> str:
            """
            Ask the user clarifying questions before generating the report.
            Call this ONCE at the start of a new research session with 1–3 multiple-choice questions.
            Each question must have a 'question' key (string) and an 'options' key (list of 3–4 strings).
            Example: [{"question": "What is your time horizon?", "options": ["1 day", "1 week", "1 month", "3+ months"]}]
            Do NOT call this tool more than once per session.
            """
            session.pending_questions = questions
            return "Questions captured. Waiting for user answers before generating the report."

        @tool
        def generate_report(config: RunnableConfig) -> str:
            """
            Trigger report generation when you have gathered enough context from the user.
            Call this after asking 1-2 relevant questions. Do NOT call immediately.
            """
            context_str = "\n".join(
                f"User: {m['content']}"
                for m in session.conversation_history
                if m.get("role") == "user"
            )
            try:
                from spend_budget import get_spend_budget_usd

                result = run_research(
                    ticker=ticker,
                    trade_type=trade_type,
                    conversation_context=context_str,
                    user_id=session.user_id,
                    emitter=session._emitter,
                    spend_budget_usd=get_spend_budget_usd(session.user_id),
                    parent_config=config,
                    username=session.username,
                )
                session.current_report_id = result.get("report_id", "")
                session.last_report_text = result.get("report_text", "")
                report_id_short = (
                    session.current_report_id[:8]
                    if session.current_report_id
                    else "unknown"
                )
                return (
                    f"Report generated successfully! Report ID: {report_id_short}...\n\n"
                    "The comprehensive research report has been created and is ready to view."
                )
            except Exception as e:
                return f"Error generating report: {e}"

        llm = ChatGoogleGenerativeAI(
            model=ORCHESTRATOR_MODEL,
            temperature=0.7,
            max_output_tokens=ORCHESTRATOR_MAX_OUTPUT_TOKENS,
        )

        agent = create_react_agent(
            llm,
            [ask_user_questions, generate_report],
            prompt=system_instructions,
        )

        # Build message history (last 4 non-system messages)
        recent = [m for m in self.conversation_history[-4:] if m["role"] != "system"]
        messages = []
        for m in recent:
            if m["role"] == "user":
                messages.append(HumanMessage(content=m["content"][:1000]))
            elif m["role"] == "assistant":
                messages.append(AIMessage(content=m["content"][:1000]))

        # Ensure current user message is last
        if not messages or not isinstance(messages[-1], HumanMessage):
            messages.append(HumanMessage(content=user_message[:1000]))

        try:
            result = agent.invoke({"messages": messages})
            response_text = ""
            for msg in reversed(result["messages"]):
                if (
                    isinstance(msg, AIMessage)
                    and msg.content
                    and not getattr(msg, "tool_calls", None)
                ):
                    content = msg.content
                    response_text = (
                        "\n".join(
                            (
                                part.get("text", "")
                                if isinstance(part, dict)
                                else str(part)
                            )
                            for part in content
                        )
                        if isinstance(content, list)
                        else str(content)
                    )
                    break
            self.conversation_history.append(
                {"role": "assistant", "content": response_text}
            )
            return response_text
        except Exception as e:
            error_msg = f"Error generating response: {e}"
            logger.exception("Orchestrator response failed")
            return error_msg

    def generate_report(
        self,
        context: str = "",
        selected_subjects: Optional[List[str]] = None,
        spend_budget_usd: Optional[float] = None,
    ) -> str:
        """Directly trigger report generation (used by app.py background threads)."""
        if not self.current_ticker or not self.current_trade_type:
            return "Error: No active research session."

        if spend_budget_usd is None:
            # Budget enforcement defaults (disabled when not configured).
            from spend_budget import get_spend_budget_usd

            spend_budget_usd = get_spend_budget_usd(self.user_id)

        try:
            result = run_research(
                ticker=self.current_ticker,
                trade_type=self.current_trade_type,
                conversation_context=context,
                user_id=self.user_id,
                emitter=self._emitter,
                selected_subjects=selected_subjects,
                spend_budget_usd=spend_budget_usd,
                username=self.username,
            )
            self.current_report_id = result.get("report_id", "")
            self.last_report_text = result.get("report_text", "")
            return self.last_report_text
        except Exception as e:
            error_msg = f"Error generating report: {e}"
            logger.exception("Report generation failed")
            return error_msg

    def chat_with_report(self, question: str) -> str:
        """Chat with the current report using RAG-lite."""
        if not self.current_report_id:
            return "Error: No report available. Please generate a report first."
        if self._emitter:
            self._emitter.emit("Searching report...")
        return self._chat_agent.chat_with_report(
            report_id=self.current_report_id,
            question=question,
        )

    def reset_conversation(self):
        self.conversation_history = []
        self.current_ticker = None
        self.current_trade_type = None
        self.current_report_id = None
        self.pending_questions = []
        self._chat_agent.reset_conversation()


def create_session(user_id: Optional[int] = None) -> OrchestratorSession:
    """Create a new orchestrator session."""
    return OrchestratorSession(user_id=user_id)
