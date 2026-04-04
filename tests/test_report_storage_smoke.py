"""
Smoke test: schema init + report storage with a long section name.
Tests the fix for MySQL key-too-long error on report_chunks.section index.
"""
import sys
import os
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from database import DatabaseManager


def run():
    print("=== Report Storage Smoke Test ===\n")

    # 1. Schema init (previously failing step)
    print("Step 1: Init schema...")
    db = DatabaseManager()
    db.init_schema()
    print("  PASS: schema initialized\n")

    # 2. Save a report
    print("Step 2: Save report...")
    long_report = "# AAPL Investment Report\n\n" + ("Lorem ipsum dolor sit amet. " * 200)
    report_id = db.save_report(
        ticker="AAPL",
        trade_type="investment",
        report_text=long_report,
        metadata={"test": True},
        user_id=None
    )
    print(f"  PASS: report saved (id={report_id})\n")

    # 3. Save chunks with a long section name (stress-tests the prefix index)
    print("Step 3: Save chunks with long section name...")
    long_section = "Earnings & Financials — Detailed Quarterly Breakdown with Year-over-Year Comparisons " * 5
    chunks = [
        {
            "chunk_text": "Chunk text " * 50,
            "section": long_section[:900],   # under VARCHAR(1000)
            "chunk_index": 0,
            "embedding": [0.1] * 50           # small fake embedding
        },
        {
            "chunk_text": "Another chunk " * 50,
            "section": "Company Overview",
            "chunk_index": 1,
            "embedding": [0.2] * 50
        }
    ]
    db.save_chunks(report_id, chunks)
    print("  PASS: chunks saved\n")

    # 4. Retrieve and verify
    print("Step 4: Retrieve report and chunks...")
    report = db.get_report(report_id)
    assert report is not None, "Report not found after save"
    assert report["ticker"] == "AAPL"

    retrieved_chunks = db.get_chunks_by_report(report_id)
    assert len(retrieved_chunks) == 2, f"Expected 2 chunks, got {len(retrieved_chunks)}"
    print(f"  PASS: retrieved report + {len(retrieved_chunks)} chunks\n")

    # 5. Cleanup
    print("Step 5: Delete test report...")
    db.delete_report(report_id)
    assert db.get_report(report_id) is None, "Report should be gone after delete"
    print("  PASS: cleanup complete\n")

    print("=== All steps passed ===")


if __name__ == "__main__":
    run()
