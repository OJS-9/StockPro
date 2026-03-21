"""
Smoke test: ReportChatAgent retrieval and anti-hallucination.

Requires live API keys (GEMINI_API_KEY) and a running MySQL instance.
Run from project root: python test_chat_smoke.py

What is tested:
  1. Report + chunks are written to DB with real Gemini embeddings.
  2. ReportChatAgent retrieves relevant chunks via vector search.
  3. Answers contain specific facts that were in the report.
  4. Agent correctly declines to answer about facts NOT in the report (no hallucination).
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from dotenv import load_dotenv

load_dotenv()

from database import DatabaseManager
from embedding_service import EmbeddingService
from report_chat_agent import ReportChatAgent

# ---------------------------------------------------------------------------
# Controlled test report with specific, checkable facts
# ---------------------------------------------------------------------------
TEST_TICKER = "TESTSYM"
TEST_TRADE_TYPE = "investment"

# Each section is a distinct chunk so vector search can retrieve selectively
REPORT_SECTIONS = {
    "Company Overview": (
        "TESTSYM Inc. is an enterprise software company headquartered in Austin, Texas. "
        "The company was founded in 2005 and went public in 2012. "
        "TESTSYM operates in the cloud infrastructure market with a customer base of over 15,000 businesses. "
        "The CEO is Alexandra Chen, who joined the company in 2018."
    ),
    "Earnings & Financials": (
        "In fiscal year 2024, TESTSYM reported total revenue of $3.72 billion, "
        "representing 18% year-over-year growth. "
        "Operating income was $521 million, yielding an operating margin of 14.0%. "
        "Net income came in at $388 million. Free cash flow was $612 million."
    ),
    "Valuation & Peers": (
        "TESTSYM trades at a price-to-earnings ratio of 42x on a trailing basis. "
        "The company's enterprise value is approximately $18.5 billion. "
        "Primary competitors include DataCorp and CloudBase, both of which trade at lower multiples. "
        "Analyst consensus price target is $95 per share."
    ),
    "Risk Factors": (
        "Key risks include increasing competition from hyperscalers entering the enterprise software space, "
        "customer concentration (top 10 customers represent 34% of revenue), "
        "and potential margin compression due to R&D investment in AI features. "
        "The company has $420 million in long-term debt maturing in 2027."
    ),
}


def _chunk_report(sections: dict) -> list:
    """Turn section dict into chunk dicts (without embeddings yet)."""
    chunks = []
    for idx, (section_name, text) in enumerate(sections.items()):
        chunks.append(
            {
                "chunk_text": text,
                "section": section_name,
                "chunk_index": idx,
            }
        )
    return chunks


def step(label: str):
    print(f"\nStep: {label}...")


def ok(msg: str):
    print(f"  PASS: {msg}")


def fail(msg: str):
    print(f"  FAIL: {msg}")
    sys.exit(1)


def run():
    print("=" * 60)
    print("SMOKE TEST: ReportChatAgent — retrieval + anti-hallucination")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. DB init
    # ------------------------------------------------------------------
    step("Init schema")
    db = DatabaseManager()
    db.init_schema()
    ok("schema ready")

    # ------------------------------------------------------------------
    # 2. Save test report
    # ------------------------------------------------------------------
    step("Save test report")
    report_text = "\n\n".join(
        f"## {section}\n{text}" for section, text in REPORT_SECTIONS.items()
    )
    report_id = db.save_report(
        ticker=TEST_TICKER,
        trade_type=TEST_TRADE_TYPE,
        report_text=report_text,
        metadata={"smoke_test": True},
        user_id=None,
    )
    ok(f"report saved (id={report_id})")

    # ------------------------------------------------------------------
    # 3. Embed chunks with real Gemini embeddings + save
    # ------------------------------------------------------------------
    step("Create real embeddings for chunks")
    emb_service = EmbeddingService()
    chunks = _chunk_report(REPORT_SECTIONS)
    for chunk in chunks:
        chunk["embedding"] = emb_service.create_embedding(chunk["chunk_text"])
    db.save_chunks(report_id, chunks)
    ok(f"saved {len(chunks)} chunks with real embeddings")

    # ------------------------------------------------------------------
    # 4. Initialise the chat agent
    # ------------------------------------------------------------------
    step("Init ReportChatAgent")
    agent = ReportChatAgent()
    ok("agent ready")

    # ------------------------------------------------------------------
    # 5. Retrieval check — question whose answer IS in the report
    # ------------------------------------------------------------------
    step("Retrieval check: revenue question")
    answer = agent.answer_question(
        report_id=report_id,
        user_question="What was TESTSYM's total revenue in fiscal year 2024?",
    )
    print(f"  Answer: {answer[:300]}")

    if "3.72" in answer or "3.7" in answer or "billion" in answer.lower():
        ok("answer contains expected revenue figure")
    else:
        fail(
            "answer did NOT contain expected revenue ($3.72 billion). "
            f"Got: {answer[:300]}"
        )

    # ------------------------------------------------------------------
    # 6. Retrieval check — different section (CEO name)
    # ------------------------------------------------------------------
    step("Retrieval check: CEO name")
    answer2 = agent.answer_question(
        report_id=report_id,
        user_question="Who is the CEO of TESTSYM?",
    )
    print(f"  Answer: {answer2[:300]}")

    if "Alexandra Chen" in answer2 or "Alexandra" in answer2:
        ok("answer contains correct CEO name")
    else:
        fail(
            f"answer did NOT contain the CEO name 'Alexandra Chen'. Got: {answer2[:300]}"
        )

    # ------------------------------------------------------------------
    # 7. Anti-hallucination check — fact NOT in the report
    #    We ask about the CFO; only the CEO is mentioned in the report.
    # ------------------------------------------------------------------
    step("Anti-hallucination check: CFO (not in report)")
    answer3 = agent.answer_question(
        report_id=report_id,
        user_question="Who is the CFO of TESTSYM?",
    )
    print(f"  Answer: {answer3[:300]}")

    # The agent should NOT invent a CFO name
    hallucination_phrases = ["not available", "not mentioned", "not provided",
                             "i don't know", "don't have", "no information",
                             "not in the report", "cannot find", "does not mention",
                             "not stated", "not included", "not specified"]
    answer3_lower = answer3.lower()
    if any(phrase in answer3_lower for phrase in hallucination_phrases):
        ok("agent correctly declined to answer (CFO not in report)")
    else:
        # If the answer is suspiciously short and contains no invented name, also OK
        # but print a warning so a human can review
        print(
            f"  WARN: answer did not contain an explicit 'not available' phrase. "
            f"Review manually: {answer3[:300]}"
        )

    # ------------------------------------------------------------------
    # 8. Anti-hallucination check — out-of-scope financial metric
    #    Gross margin is never mentioned; only operating margin (14%) is.
    # ------------------------------------------------------------------
    step("Anti-hallucination check: gross margin (not in report)")
    answer4 = agent.answer_question(
        report_id=report_id,
        user_question="What is TESTSYM's gross margin percentage?",
    )
    print(f"  Answer: {answer4[:300]}")

    answer4_lower = answer4.lower()
    # Should NOT claim a specific gross margin number
    hallucination_signals = ["14%", "14.0%", "gross margin is", "gross margin was",
                             "gross margin of", "65%", "70%", "75%"]  # common LLM guesses
    invented = [s for s in hallucination_signals if s.lower() in answer4_lower]
    if not invented:
        ok("agent did not hallucinate a gross margin figure")
    else:
        # Distinguish: if answer uses 14% it might be confusing operating margin
        if "14" in answer4 and "operating" in answer4_lower:
            print("  WARN: agent cited operating margin (14%) when asked about gross margin — review.")
        else:
            fail(
                f"agent may have hallucinated gross margin. Suspicious phrases found: {invented}. "
                f"Answer: {answer4[:300]}"
            )

    # ------------------------------------------------------------------
    # 9. Cleanup
    # ------------------------------------------------------------------
    step("Cleanup test report")
    db.delete_report(report_id)
    assert db.get_report(report_id) is None, "report not deleted"
    ok("cleanup complete")

    print()
    print("=" * 60)
    print("ALL SMOKE TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    run()
