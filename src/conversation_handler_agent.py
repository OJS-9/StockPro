"""
Conversation handler agent for answering questions after report generation.
Uses both the synthesized report (via RAG) and raw research outputs.
"""

import os
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

from agents import Agent, Runner, trace, ModelSettings

from embedding_service import EmbeddingService
from vector_search import VectorSearch
from report_storage import ReportStorage
from research_prompt import get_conversation_handler_instructions

load_dotenv()


class ConversationHandlerAgent:
    """Agent for handling post-report conversations using report and research outputs."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY environment variable.")

        self.embedding_service = EmbeddingService(api_key=self.api_key)
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
        top_k: int = 5
    ) -> str:
        """
        Answer a question about a report using RAG retrieval and raw research outputs.

        Args:
            report_id: Report ID
            user_question: User's question
            ticker: Stock ticker symbol
            trade_type: Type of trade
            conversation_history: Previous conversation turns (optional)
            top_k: Number of chunks to retrieve from report

        Returns:
            Agent's answer based on report excerpts and research outputs
        """
        query_embedding = self.embedding_service.create_embedding(user_question)

        relevant_chunks = self.vector_search.search_chunks(
            report_id=report_id,
            query_embedding=query_embedding,
            top_k=top_k
        )

        research_outputs = self.report_storage.get_research_outputs(report_id)

        if not relevant_chunks and not research_outputs:
            return "I couldn't find relevant information to answer your question. The report or research data may not be available."

        prompt = self._build_prompt(
            question=user_question,
            report_chunks=relevant_chunks or [],
            research_outputs=research_outputs or {},
            conversation_history=conversation_history or self.conversation_history
        )

        system_instructions = get_conversation_handler_instructions(ticker, trade_type)

        agent = Agent(
            name="Conversation Handler Agent",
            instructions=system_instructions,
            model="gpt-4o",
            tools=[],
            model_settings=ModelSettings(temperature=0.7)
        )

        try:
            with trace("Conversation Handler", metadata={
                "report_id": report_id,
                "chunks_retrieved": str(len(relevant_chunks)),
                "research_outputs_count": str(len(research_outputs) if research_outputs else 0)
            }):
                result = Runner.run_sync(agent, prompt, max_turns=5)

            if hasattr(result, 'final_output'):
                return result.final_output
            elif hasattr(result, 'output'):
                return result.output
            elif isinstance(result, str):
                return result
            return str(result)

        except Exception as e:
            error_msg = f"Error generating answer: {str(e)}"
            print(error_msg)
            return error_msg

    def _build_prompt(
        self,
        question: str,
        report_chunks: List[Dict[str, Any]],
        research_outputs: Dict[str, Dict[str, Any]],
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        prompt_parts = []

        if report_chunks:
            prompt_parts.append("=== REPORT EXCERPTS ===\n")
            for i, chunk in enumerate(report_chunks, 1):
                section_info = f" (Section: {chunk.get('section', 'Unknown')})" if chunk.get('section') else ""
                prompt_parts.append(f"[Report Excerpt {i}{section_info}]")
                prompt_parts.append(chunk['chunk_text'])
                prompt_parts.append("")

        if research_outputs:
            prompt_parts.append("=== RAW RESEARCH OUTPUTS ===\n")
            prompt_parts.append(self._format_research_outputs(research_outputs))
            prompt_parts.append("")

        prompt_parts.append("---\n")

        if conversation_history:
            prompt_parts.append("Previous conversation:")
            for turn in conversation_history[-3:]:
                role = turn.get('role', 'user')
                content = turn.get('content', '')
                if role in ['user', 'assistant']:
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
            subject_name = result.get('subject_name', subject_id)
            research_output = result.get('research_output', '')

            formatted_parts.append(f"[Research Subject: {subject_name} (ID: {subject_id})]")
            formatted_parts.append(research_output)

            sources = result.get('sources', [])
            if sources:
                formatted_parts.append("\nSources:")
                for source in sources[:3]:
                    if isinstance(source, dict):
                        tool_name = source.get('tool', source.get('name', 'Unknown'))
                        formatted_parts.append(f"  - {tool_name}")

            formatted_parts.append("")
            formatted_parts.append("---\n")

        return "\n".join(formatted_parts)

    def reset_conversation(self):
        """Reset conversation history."""
        self.conversation_history = []
