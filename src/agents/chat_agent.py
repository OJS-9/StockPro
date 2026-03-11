"""
RAG-lite chat agent for answering questions about stored reports.
Merges report_chat_agent.py + conversation_handler_agent.py into one LangChain chain.
"""

import os
from typing import List, Dict, Any, Optional

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from embedding_service import EmbeddingService
from vector_search import VectorSearch
from date_utils import get_datetime_context_string

CHAT_MODEL = os.getenv("CHAT_AGENT_MODEL", "gemini-2.0-flash-exp")


def _get_system_instructions() -> str:
    datetime_context = get_datetime_context_string()
    return f"""You are a research assistant that answers questions about company research reports.

{datetime_context}

**CRITICAL RULES:**
1. You MUST answer questions using ONLY the information provided in the report excerpts below.
2. If the information needed to answer the question is NOT in the provided excerpts, say "I don't know from this report" or "This information is not available in the report."
3. DO NOT use any knowledge outside of the provided report excerpts.
4. DO NOT make up information or infer details not explicitly stated in the excerpts.
5. When citing information, reference the section or context from the excerpts.

**Guidelines:**
- Be precise and accurate
- Cite specific information from the excerpts when possible
- If the question requires information from multiple sections, synthesize across the provided excerpts
- Keep answers concise but complete"""


def _build_rag_prompt(
    question: str,
    chunks: List[Dict[str, Any]],
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> str:
    prompt_parts = ["Relevant excerpts from the report:", ""]

    for i, chunk in enumerate(chunks, 1):
        section_info = f" (Section: {chunk.get('section', 'Unknown')})" if chunk.get("section") else ""
        prompt_parts.append(f"[Excerpt {i}{section_info}]")
        prompt_parts.append(chunk["chunk_text"])
        prompt_parts.append("")

    prompt_parts.append("---")
    prompt_parts.append("")

    if conversation_history:
        prompt_parts.append("Previous conversation:")
        for turn in conversation_history[-3:]:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role in ("user", "assistant"):
                prompt_parts.append(f"{role.capitalize()}: {content}")
        prompt_parts.append("")

    prompt_parts.append(f"User question: {question}")
    prompt_parts.append("")
    prompt_parts.append(
        "Answer the question using ONLY the information from the report excerpts above. "
        "If the information is not available in the excerpts, say so clearly."
    )

    return "\n".join(prompt_parts)


class ReportChatAgent:
    """LangChain RAG chain for chatting with stored research reports."""

    def __init__(self):
        self._embedding_service = EmbeddingService()
        self._vector_search = VectorSearch()
        self._llm = ChatGoogleGenerativeAI(model=CHAT_MODEL, temperature=0.7)
        self.conversation_history: List[Dict[str, str]] = []

    def answer_question(
        self,
        report_id: str,
        user_question: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        top_k: int = 5,
    ) -> str:
        """Answer a question about a report using RAG-lite retrieval."""
        query_embedding = self._embedding_service.create_embedding(user_question)
        relevant_chunks = self._vector_search.search_chunks(
            report_id=report_id,
            query_embedding=query_embedding,
            top_k=top_k,
        )

        if not relevant_chunks:
            return (
                "I couldn't find relevant information in the report to answer your question. "
                "The report may not contain information about this topic."
            )

        prompt = _build_rag_prompt(user_question, relevant_chunks, conversation_history)
        system_instructions = _get_system_instructions()

        try:
            response = self._llm.invoke(
                [SystemMessage(content=system_instructions), HumanMessage(content=prompt)]
            )
            return response.content or ""
        except Exception as e:
            error_msg = f"Error generating answer: {e}"
            print(error_msg)
            return error_msg

    def chat_with_report(self, report_id: str, question: str, reset_history: bool = False) -> str:
        """Chat with a report, maintaining conversation history."""
        if reset_history:
            self.conversation_history = []

        answer = self.answer_question(
            report_id=report_id,
            user_question=question,
            conversation_history=self.conversation_history,
        )

        self.conversation_history.append({"role": "user", "content": question})
        self.conversation_history.append({"role": "assistant", "content": answer})

        return answer

    def reset_conversation(self):
        self.conversation_history = []
