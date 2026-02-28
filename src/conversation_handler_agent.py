"""
Conversation handler agent for answering questions after report generation.
Uses both the synthesized report (via RAG) and raw research outputs.
"""

import os
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

from google import genai
from google.genai import types

from embedding_service import EmbeddingService
from vector_search import VectorSearch
from report_storage import ReportStorage
from research_prompt import get_conversation_handler_instructions

load_dotenv()

CHAT_AGENT_MODEL = os.getenv("CHAT_AGENT_MODEL", "gemini-2.0-flash")


class ConversationHandlerAgent:
    """Agent for handling post-report conversations using report and research outputs."""

    def __init__(self, api_key: Optional[str] = None):
        # api_key kept for interface compatibility; Gemini key comes from env
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            raise ValueError("GEMINI_API_KEY is required. Set it in your .env file.")

        self._client = genai.Client(api_key=gemini_key)
        self.embedding_service = EmbeddingService()
        self.vector_search = VectorSearch()
        self.report_storage = ReportStorage()
        self.conversation_history: List[Dict[str, str]] = []

    def answer_question(
        self,
        report_id: str,
        user_question: str,
        ticker: str,
        trade_type: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        top_k: int = 5,
    ) -> str:
        """Answer a question about a report using RAG retrieval and raw research outputs."""
        query_embedding = self.embedding_service.create_embedding(user_question)
        relevant_chunks = self.vector_search.search_chunks(
            report_id=report_id,
            query_embedding=query_embedding,
            top_k=top_k,
        )

        research_outputs = self.report_storage.get_research_outputs(report_id)

        if not relevant_chunks and not research_outputs:
            return "I couldn't find relevant information to answer your question. The report or research data may not be available."

        prompt = self._build_prompt(
            question=user_question,
            report_chunks=relevant_chunks or [],
            research_outputs=research_outputs or {},
            conversation_history=conversation_history or self.conversation_history,
        )

        system_instructions = get_conversation_handler_instructions(ticker, trade_type)

        try:
            response = self._client.models.generate_content(
                model=CHAT_AGENT_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instructions,
                    temperature=0.7,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            return response.text or ""
        except Exception as e:
            error_msg = f"Error generating answer: {e}"
            print(error_msg)
            return error_msg

    def _build_prompt(
        self,
        question: str,
        report_chunks: List[Dict[str, Any]],
        research_outputs: Dict[str, Dict[str, Any]],
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        prompt_parts = []

        if report_chunks:
            prompt_parts.append("=== REPORT EXCERPTS ===\n")
            for i, chunk in enumerate(report_chunks, 1):
                section_info = f" (Section: {chunk.get('section', 'Unknown')})" if chunk.get("section") else ""
                prompt_parts.append(f"[Report Excerpt {i}{section_info}]")
                prompt_parts.append(chunk["chunk_text"])
                prompt_parts.append("")

        if research_outputs:
            prompt_parts.append("=== RAW RESEARCH OUTPUTS ===\n")
            prompt_parts.append(self._format_research_outputs(research_outputs))
            prompt_parts.append("")

        prompt_parts.append("---\n")

        if conversation_history:
            prompt_parts.append("Previous conversation:")
            for turn in conversation_history[-3:]:
                role = turn.get("role", "user")
                content = turn.get("content", "")
                if role in ("user", "assistant"):
                    prompt_parts.append(f"{role.capitalize()}: {content}")
            prompt_parts.append("")

        prompt_parts.append(f"User question: {question}\n")
        prompt_parts.append(
            "Answer the question using ONLY the information from the report excerpts and raw research outputs above. "
            "If the information is not available in these sources, say so clearly."
        )

        return "\n".join(prompt_parts)

    def _format_research_outputs(self, research_outputs: Dict[str, Dict[str, Any]]) -> str:
        formatted_parts = []
        for subject_id, result in research_outputs.items():
            subject_name = result.get("subject_name", subject_id)
            research_output = result.get("research_output", "")
            formatted_parts.append(f"[Research Subject: {subject_name} (ID: {subject_id})]")
            formatted_parts.append(research_output)
            sources = result.get("sources", [])
            if sources:
                formatted_parts.append("\nSources:")
                for source in sources[:3]:
                    if isinstance(source, dict):
                        tool_name = source.get("tool", source.get("name", "Unknown"))
                        formatted_parts.append(f"  - {tool_name}")
            formatted_parts.append("")
            formatted_parts.append("---\n")
        return "\n".join(formatted_parts)

    def reset_conversation(self):
        self.conversation_history = []
