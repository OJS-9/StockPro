from report_quality import assess_report_structure


def test_plain_text_no_headings_passes():
    ok, missing = assess_report_structure("No markdown headings here.")
    assert ok is True
    assert missing == []


def test_full_headings_passes():
    text = """## Executive Summary
ok
## Risk Factors
ok
## Recommendation
ok
"""
    ok, missing = assess_report_structure(text)
    assert ok is True
    assert missing == []


def test_missing_risk():
    text = """## Summary
x
## Recommendation
y
"""
    ok, missing = assess_report_structure(text)
    assert ok is False
    assert "risk" in missing


def test_missing_multiple():
    text = "## Summary\nonly one"
    ok, missing = assess_report_structure(text)
    assert ok is False
    assert "risk" in missing
    assert "recommendation" in missing
