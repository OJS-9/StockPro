"""
PDF generation service for stock research reports.
Uses WeasyPrint to convert markdown reports to PDF.
"""

import io
import markdown
from datetime import datetime
from weasyprint import HTML, CSS


class PDFGenerator:
    """Service for generating PDF exports of stock research reports."""

    # Print-friendly CSS styling
    PDF_CSS = """
    @page {
        size: A4;
        margin: 2cm;
        @bottom-center {
            content: "Page " counter(page) " of " counter(pages);
            font-size: 10px;
            color: #666;
        }
    }

    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
        font-size: 12px;
        line-height: 1.6;
        color: #1a1a1a;
        max-width: 100%;
    }

    .report-header {
        border-bottom: 2px solid #10b981;
        padding-bottom: 1em;
        margin-bottom: 2em;
    }

    .report-header h1 {
        font-size: 24px;
        margin: 0 0 0.5em 0;
        color: #1a1a1a;
    }

    .report-meta {
        display: flex;
        gap: 2em;
        color: #666;
        font-size: 11px;
    }

    .report-meta span {
        display: inline-block;
    }

    .ticker-badge {
        background: #10b981;
        color: white;
        padding: 0.25em 0.75em;
        border-radius: 4px;
        font-weight: bold;
        font-size: 14px;
    }

    .trade-type-badge {
        background: #f3f4f6;
        color: #374151;
        padding: 0.25em 0.75em;
        border-radius: 4px;
        font-size: 12px;
    }

    .report-content h1 {
        font-size: 20px;
        color: #1a1a1a;
        border-bottom: 1px solid #e5e7eb;
        padding-bottom: 0.5em;
        margin-top: 1.5em;
    }

    .report-content h2 {
        font-size: 16px;
        color: #374151;
        margin-top: 1.25em;
    }

    .report-content h3 {
        font-size: 14px;
        color: #4b5563;
        margin-top: 1em;
    }

    .report-content p {
        margin: 0.75em 0;
        text-align: justify;
    }

    .report-content ul, .report-content ol {
        margin: 0.75em 0;
        padding-left: 1.5em;
    }

    .report-content li {
        margin: 0.25em 0;
    }

    .report-content strong {
        color: #1a1a1a;
    }

    .report-content blockquote {
        border-left: 3px solid #10b981;
        margin: 1em 0;
        padding: 0.5em 1em;
        background: #f9fafb;
        color: #4b5563;
    }

    .report-content code {
        background: #f3f4f6;
        padding: 0.15em 0.4em;
        border-radius: 3px;
        font-family: 'SF Mono', Monaco, 'Courier New', monospace;
        font-size: 11px;
    }

    .report-content pre {
        background: #1f2937;
        color: #f9fafb;
        padding: 1em;
        border-radius: 6px;
        overflow-x: auto;
        font-size: 11px;
    }

    .report-content pre code {
        background: none;
        padding: 0;
        color: inherit;
    }

    .report-content table {
        width: 100%;
        border-collapse: collapse;
        margin: 1em 0;
        font-size: 11px;
    }

    .report-content th, .report-content td {
        border: 1px solid #e5e7eb;
        padding: 0.5em;
        text-align: left;
    }

    .report-content th {
        background: #f9fafb;
        font-weight: 600;
    }

    .report-footer {
        margin-top: 2em;
        padding-top: 1em;
        border-top: 1px solid #e5e7eb;
        font-size: 10px;
        color: #9ca3af;
        text-align: center;
    }
    """

    def __init__(self):
        """Initialize PDF generator."""
        self.md = markdown.Markdown(
            extensions=['tables', 'fenced_code', 'nl2br', 'sane_lists']
        )

    def generate_pdf(
        self,
        ticker: str,
        trade_type: str,
        report_text: str,
        created_at: datetime = None
    ) -> bytes:
        """
        Generate a PDF from a stock research report.

        Args:
            ticker: Stock ticker symbol
            trade_type: Type of trade (Investment, Day Trade, Swing Trade)
            report_text: Full report text in markdown format
            created_at: Report creation timestamp

        Returns:
            PDF file as bytes
        """
        if created_at is None:
            created_at = datetime.now()

        # Convert markdown to HTML
        self.md.reset()
        report_html = self.md.convert(report_text)

        # Format date
        date_str = created_at.strftime("%B %d, %Y at %I:%M %p")

        # Build full HTML document
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{ticker} Research Report</title>
        </head>
        <body>
            <div class="report-header">
                <h1>
                    <span class="ticker-badge">{ticker}</span>
                    Stock Research Report
                </h1>
                <div class="report-meta">
                    <span class="trade-type-badge">{trade_type}</span>
                    <span>Generated: {date_str}</span>
                </div>
            </div>

            <div class="report-content">
                {report_html}
            </div>

            <div class="report-footer">
                Generated by StockIntel AI | This report is for informational purposes only and does not constitute financial advice.
            </div>
        </body>
        </html>
        """

        # Generate PDF
        pdf_buffer = io.BytesIO()
        HTML(string=html_content).write_pdf(
            pdf_buffer,
            stylesheets=[CSS(string=self.PDF_CSS)]
        )
        pdf_buffer.seek(0)

        return pdf_buffer.getvalue()


# Global instance for convenience
_pdf_generator = None


def get_pdf_generator() -> PDFGenerator:
    """Get or create global PDF generator instance."""
    global _pdf_generator
    if _pdf_generator is None:
        _pdf_generator = PDFGenerator()
    return _pdf_generator
