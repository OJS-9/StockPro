"""
App-layer user scoping for reports (complements Supabase RLS for PostgREST/direct roles).

DatabaseManager.get_report(report_id, user_id=...) uses a scoped query; ReportStorage
delegates with the same contract.
"""

from unittest.mock import MagicMock

from report_storage import ReportStorage


def test_report_storage_get_report_passes_user_id_for_ownership():
    # Avoid EmbeddingService init (requires GEMINI_API_KEY in CI).
    storage = ReportStorage.__new__(ReportStorage)
    mock_db = MagicMock()
    mock_db.get_report.return_value = None
    storage._db = mock_db

    storage.get_report("report-uuid-1", user_id="user-a")

    mock_db.get_report.assert_called_once_with("report-uuid-1", user_id="user-a")


def test_supabase_doc_mentions_rls():
    """Docs stay aligned with [STOA-4](/STOA/issues/STOA-4#document-plan) Supabase verification."""
    from pathlib import Path

    doc = Path(__file__).resolve().parents[1] / "docs" / "SUPABASE.md"
    text = doc.read_text(encoding="utf-8")
    assert "Row Level Security" in text or "RLS" in text
