"""
RAG-lite chat agent for answering questions about stored reports.
Merges report_chat_agent.py + conversation_handler_agent.py into one LangChain chain.
"""

import os
from typing import List, Dict, Any, Optional

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from langsmith import traceable

from embedding_service import EmbeddingService
from vector_search import VectorSearch
from date_utils import get_datetime_context_string

CHAT_MODEL = os.getenv("CHAT_AGENT_MODEL", "gemini-2.5-flash")
CHAT_TOP_K = int(os.getenv("CHAT_TOP_K", "5"))


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
- Keep answers concise but complete
- Excerpts tagged [Report] are from the final synthesized report. Excerpts tagged [Raw Research] contain detailed research notes. Both are valid. Prefer [Report] when sufficient; use [Raw Research] for deeper detail."""


def _build_rag_prompt(
    question: str,
    chunks: List[Dict[str, Any]],
    conversation_history: Optional[List[Dict[str, str]]] = None,
) -> str:
    prompt_parts = ["Relevant excerpts from the report:", ""]

    for i, chunk in enumerate(chunks, 1):
        section_info = f" (Section: {chunk.get('section', 'Unknown')})" if chunk.get("section") else ""
        source_label = " | Raw Research" if chunk.get('chunk_type') == 'research' else " | Report"
        prompt_parts.append(f"[Excerpt {i}{section_info}{source_label}]")
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
        self._llm = ChatGoogleGenerativeAI(model=CHAT_MODEL, temperature=0.7, timeout=90)
        self.conversation_history: List[Dict[str, str]] = []

    FALLBACK_THRESHOLD = float(os.getenv("RESEARCH_FALLBACK_THRESHOLD", "0.45"))

    @traceable(run_type="retriever", name="ReportChat Retrieval")
    def _retrieve_chunks(
        self,
        report_id: str,
        user_question: str,
        top_k: int = CHAT_TOP_K,
    ) -> List[Dict[str, Any]]:
        """Embed query and retrieve relevant chunks via two-phase vector search."""
        print(f"[ReportChat] Creating query embedding...")
        query_embedding = self._embedding_service.create_embedding(user_question)
        print(f"[ReportChat] Embedding created (dim={len(query_embedding)})")

        # Phase 1: search report chunks
        print("[ReportChat] Phase 1: searching report chunks...")
        report_chunks = self._vector_search.search_chunks(
            report_id=report_id,
            query_embedding=query_embedding,
            top_k=top_k,
            chunk_type='report',
        )
        print(f"[ReportChat] Phase 1: found {len(report_chunks)} report chunks")

        # Phase 2: conditionally fetch research chunks if report scores are low
        best_score = report_chunks[0]['similarity_score'] if report_chunks else 0.0
        if best_score < self.FALLBACK_THRESHOLD or len(report_chunks) < 2:
            print(f"[ReportChat] Phase 2: best_score={best_score:.3f} < threshold={self.FALLBACK_THRESHOLD}, fetching research chunks...")
            research_chunks = self._vector_search.search_chunks(
                report_id=report_id,
                query_embedding=query_embedding,
                top_k=3,
                chunk_type='research',
            )
            print(f"[ReportChat] Phase 2: found {len(research_chunks)} research chunks")
            all_chunks = report_chunks + research_chunks
        else:
            all_chunks = report_chunks

        # Deduplicate and cap
        seen = set()
        relevant_chunks = []
        for c in sorted(all_chunks, key=lambda x: x['similarity_score'], reverse=True):
            if c['chunk_id'] not in seen:
                seen.add(c['chunk_id'])
                relevant_chunks.append(c)
        relevant_chunks = relevant_chunks[:top_k + 2]
        print(f"[ReportChat] {len(relevant_chunks)} chunks after dedup/cap")
        return relevant_chunks

    @traceable(run_type="chain", name="ReportChat RAG")
    def answer_question(
        self,
        report_id: str,
        user_question: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        top_k: int = CHAT_TOP_K,
    ) -> str:
        """Answer a question about a report using RAG-lite retrieval with conditional research fallback."""
        print(f"[ReportChat] answer_question called — report_id={report_id}, question={user_question[:80]!r}")

        relevant_chunks = self._retrieve_chunks(report_id, user_question, top_k)

        if not relevant_chunks:
            print("[ReportChat] No relevant chunks found — returning fallback message")
            return (
                "I couldn't find relevant information in the report to answer your question. "
                "The report may not contain information about this topic."
            )

        prompt = _build_rag_prompt(user_question, relevant_chunks, conversation_history)
        system_instructions = _get_system_instructions()

        try:
            print(f"[ReportChat] Calling LLM ({CHAT_MODEL})...")
            response = self._llm.invoke(
                [SystemMessage(content=system_instructions), HumanMessage(content=prompt)]
            )
            print(f"[ReportChat] LLM response received ({len(response.content or '')} chars)")
            return response.content or ""
        except Exception as e:
            error_msg = f"[ReportChat] Error generating answer: {e}"
            print(error_msg)
            return error_msg

    @traceable(run_type="chain", name="ReportChat Session")
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
