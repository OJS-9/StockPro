"""
ReAct chat agent for answering questions about stored reports.
Uses LangGraph create_react_agent with report retrieval, IR search, and yfinance tools.
"""

import json
import logging
import os
from typing import List, Dict, Any, Optional

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langgraph.prebuilt import create_react_agent
from langsmith import traceable

from embedding_service import EmbeddingService
from vector_search import VectorSearch
from nimble_client import NimbleClient
from langchain_tools import create_chat_tools
from date_utils import get_datetime_context_string

logger = logging.getLogger(__name__)

CHAT_MODEL = os.getenv("CHAT_AGENT_MODEL", "gemini-2.5-flash")
CHAT_TOP_K = int(os.getenv("CHAT_TOP_K", "5"))
CHAT_RECURSION_LIMIT = int(os.getenv("CHAT_RECURSION_LIMIT", "10"))


def _get_system_instructions(ticker: str, language: Optional[str] = None) -> str:
    datetime_context = get_datetime_context_string()
    instructions = f"""You are a research assistant that answers questions about the {ticker} research report.

{datetime_context}

You have access to tools for searching the stored report, checking investor relations pages, and pulling earnings data.

WORKFLOW:
1. ALWAYS start by calling retrieve_report_chunks to search the stored report.
2. If the question involves earnings, revenue, guidance, or financial results, also call search_ir_earnings and/or get_earnings_data to cross-verify with live data.
3. Synthesize information from all sources into a clear answer.

CITATION RULES:
- Every tool result contains numbered items with an "index" field.
- ALWAYS cite by placing the index number in square brackets: [1], [2], [3], etc.
- Every factual claim MUST have at least one citation.
- You may cite multiple sources for one claim: [1][3].
- Do NOT skip citations. If you used information from a source, cite it.

GUIDELINES:
- Be precise and accurate
- Cite specific information from the report excerpts when possible
- If the question requires information from multiple sections, synthesize across sources
- If report and live data conflict, note the discrepancy and state which is more recent
- Keep answers concise but complete
- If information is not available from any source, say so clearly"""

    if language == "he":
        instructions += """

IMPORTANT: Respond entirely in Hebrew. Keep ticker symbols, company names, \
source citations [1], and numerical data in their original form. All explanations, \
analysis, and natural language must be in Hebrew."""

    return instructions


class ReportChatAgent:
    """LangGraph ReAct agent for chatting with stored research reports."""

    FALLBACK_THRESHOLD = float(os.getenv("RESEARCH_FALLBACK_THRESHOLD", "0.45"))

    def __init__(self):
        self._embedding_service = EmbeddingService()
        self._vector_search = VectorSearch()
        self._nimble_client = None
        self._llm = ChatGoogleGenerativeAI(
            model=CHAT_MODEL, temperature=0.7, timeout=90
        )
        self.conversation_history: List[Dict[str, str]] = []
        self._progress_fn = None

    def set_progress_fn(self, fn):
        """Set a callback for emitting progress messages (e.g. SSE steps)."""
        self._progress_fn = fn

    def _get_nimble_client(self) -> Optional[NimbleClient]:
        if self._nimble_client is None:
            try:
                self._nimble_client = NimbleClient()
            except ValueError:
                pass
        return self._nimble_client

    def _collect_sources(self, messages: list) -> List[Dict[str, Any]]:
        """Extract source metadata from tool call results in the message history."""
        sources = []
        source_index = 1

        for msg in messages:
            if not isinstance(msg, ToolMessage):
                continue

            tool_name = getattr(msg, "name", "")
            try:
                content = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
            except (json.JSONDecodeError, TypeError):
                continue

            if tool_name == "retrieve_report_chunks" and isinstance(content, list):
                for chunk in content:
                    sources.append({
                        "index": chunk.get("index", source_index),
                        "chunk_id": chunk.get("chunk_id"),
                        "section": chunk.get("section"),
                        "chunk_type": chunk.get("chunk_type", "report"),
                        "similarity_score": chunk.get("similarity_score"),
                        "chunk_text": chunk.get("chunk_text", ""),
                        "url": None,
                    })
                    source_index = max(source_index, chunk.get("index", 0)) + 1

            elif tool_name == "search_ir_earnings" and isinstance(content, list):
                for r in content:
                    src_type = r.get("source_type", "ir")
                    sources.append({
                        "index": r.get("index", source_index),
                        "chunk_id": None,
                        "section": r.get("title", "SEC Filing" if src_type == "sec" else "IR Search Result"),
                        "chunk_type": "sec" if src_type == "sec" else "ir",
                        "similarity_score": None,
                        "chunk_text": r.get("snippet", ""),
                        "url": r.get("url"),
                    })

            elif tool_name == "get_earnings_data" and isinstance(content, list):
                for r in content:
                    if r.get("source_type") == "yfinance":
                        data = r.get("data", {})
                        parts = []
                        eh = data.get("earnings_history", [])
                        if eh:
                            for row in eh[:4]:
                                q = row.get("index", row.get("Quarter", "?"))
                                actual = row.get("epsActual", row.get("Reported EPS", "?"))
                                est = row.get("epsEstimate", row.get("EPS Estimate", "?"))
                                parts.append(f"{q}: EPS {actual} actual vs {est} estimate")
                        ned = data.get("next_earnings_date")
                        if ned and ned != "None":
                            parts.append(f"Next earnings date: {ned}")
                        eg = data.get("earnings_growth")
                        if eg is not None:
                            parts.append(f"Earnings growth: {eg:.1%}" if isinstance(eg, (int, float)) else f"Earnings growth: {eg}")
                        te = data.get("trailing_eps")
                        fe = data.get("forward_eps")
                        if te is not None:
                            parts.append(f"Trailing EPS: {te}")
                        if fe is not None:
                            parts.append(f"Forward EPS: {fe}")
                        sources.append({
                            "index": r.get("index", 200),
                            "chunk_id": None,
                            "section": "Earnings Data (Yahoo Finance)",
                            "chunk_type": "yfinance",
                            "similarity_score": None,
                            "chunk_text": "\n".join(parts) if parts else json.dumps(data, indent=2),
                            "url": None,
                        })

        return sources

    @traceable(run_type="chain", name="ReportChat RAG")
    def answer_question(
        self,
        report_id: str,
        ticker: str,
        user_question: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        top_k: int = CHAT_TOP_K,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Answer a question about a report using a ReAct agent with report retrieval, IR search, and yfinance tools."""
        logger.debug(
            "answer_question called -- report_id=%s, ticker=%s, question=%r",
            report_id, ticker, user_question[:80],
        )

        tools = create_chat_tools(
            nimble_client=self._get_nimble_client(),
            report_id=report_id,
            ticker=ticker,
            embedding_service=self._embedding_service,
            vector_search=self._vector_search,
            progress_fn=self._progress_fn,
        )

        system_instructions = _get_system_instructions(ticker, language=language)

        agent = create_react_agent(
            self._llm,
            tools,
            prompt=system_instructions,
        )

        # Build message history (last 3 turns)
        messages = []
        if conversation_history:
            for turn in conversation_history[-3:]:
                role = turn.get("role", "user")
                content = turn.get("content", "")
                if role == "user":
                    messages.append(HumanMessage(content=content[:1000]))
                elif role == "assistant":
                    messages.append(AIMessage(content=content[:1000]))

        # Ensure current question is last
        if not messages or not isinstance(messages[-1], HumanMessage):
            messages.append(HumanMessage(content=user_question))
        elif messages[-1].content != user_question:
            messages.append(HumanMessage(content=user_question))

        try:
            logger.debug("Running ReAct agent (%s, recursion_limit=%s)", CHAT_MODEL, CHAT_RECURSION_LIMIT)
            result = agent.invoke(
                {"messages": messages},
                config={"recursion_limit": CHAT_RECURSION_LIMIT},
            )

            # Extract answer from the last non-tool-call AIMessage
            answer_text = ""
            for msg in reversed(result["messages"]):
                if (
                    isinstance(msg, AIMessage)
                    and msg.content
                    and not getattr(msg, "tool_calls", None)
                ):
                    content = msg.content
                    answer_text = (
                        "\n".join(
                            part.get("text", "") if isinstance(part, dict) else str(part)
                            for part in content
                        )
                        if isinstance(content, list)
                        else str(content)
                    )
                    break

            # Collect sources from tool call results
            all_sources = self._collect_sources(result["messages"])

            # Only include sources that were actually cited in the answer
            import re
            cited_indices = {int(m) for m in re.findall(r'\[(\d+)\]', answer_text)}
            sources = [s for s in all_sources if s["index"] in cited_indices]

            # Fallback: if no citations found but report chunks exist, include them anyway
            if not sources and all_sources:
                sources = [s for s in all_sources if s["chunk_type"] in ("report", "research")]

            logger.debug("Answer: %s chars, %s cited sources (of %s total)", len(answer_text), len(sources), len(all_sources))
            return {"answer": answer_text, "sources": sources}

        except Exception as e:
            error_msg = f"Error generating answer: {e}"
            logger.exception("Chat answer generation failed")
            return {"answer": error_msg, "sources": []}

    @traceable(run_type="chain", name="ReportChat Session")
    def chat_with_report(
        self,
        report_id: str,
        ticker: str,
        question: str,
        reset_history: bool = False,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Chat with a report, maintaining conversation history."""
        if reset_history:
            self.conversation_history = []

        result = self.answer_question(
            report_id=report_id,
            ticker=ticker,
            user_question=question,
            conversation_history=self.conversation_history,
            language=language,
        )

        self.conversation_history.append({"role": "user", "content": question})
        self.conversation_history.append({"role": "assistant", "content": result["answer"]})

        return result

    def reset_conversation(self):
        self.conversation_history = []
