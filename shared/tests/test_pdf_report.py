"""Tests for PDF report generation module."""
from unittest.mock import MagicMock, patch

import shared.pdf_report
from shared.pdf_report import _highlight_diff_words, generate_similarity_report_pdf


def test_highlight_diff_words():
    text_a = "the quick brown fox"
    text_b = "the lazy brown dog"
    hl_a, hl_b = _highlight_diff_words(text_a, text_b)
    assert "<b>the</b>" in hl_a
    assert "<b>brown</b>" in hl_a
    assert "quick" in hl_a and "<b>" not in "quick"
    assert "fox" in hl_a and "<b>" not in "fox"
    assert "lazy" in hl_b and "<b>" not in "lazy"
    assert "dog" in hl_b and "<b>" not in "dog"


def test_highlight_diff_words_identical():
    text_a = "same words here"
    hl_a, hl_b = _highlight_diff_words(text_a, text_a)
    for w in hl_a:
        assert "<b>" in w


def test_highlight_diff_words_empty():
    hl_a, hl_b = _highlight_diff_words("", "some words")
    assert hl_a == []
    assert len(hl_b) > 0


def test_generate_reportlab_success():
    old_avail = shared.pdf_report._REPORTLAB_AVAILABLE
    shared.pdf_report._REPORTLAB_AVAILABLE = True
    shared.pdf_report.SimpleDocTemplate = MagicMock()
    shared.pdf_report.getSampleStyleSheet = MagicMock()
    shared.pdf_report.ParagraphStyle = MagicMock()
    shared.pdf_report.A4 = MagicMock()
    shared.pdf_report.mm = MagicMock()
    shared.pdf_report.colors = MagicMock()
    shared.pdf_report.Spacer = MagicMock()
    shared.pdf_report.PageBreak = MagicMock()
    shared.pdf_report.Table = MagicMock()
    shared.pdf_report.TableStyle = MagicMock()
    shared.pdf_report.Paragraph = MagicMock()
    with patch("shared.pdf_report.io.BytesIO") as mock_bytes_io:
        mock_bytes_io.return_value.getvalue.return_value = b"%PDF-1.4 report data"
        try:
            result = generate_similarity_report_pdf(
                batch_name="Test Batch",
                submission_a={"roll": "A1", "name": "Alice"},
                submission_b={"roll": "B1", "name": "Bob"},
                similarity_score=0.75,
                text_a="hello world",
                text_b="hello there",
            )
        finally:
            shared.pdf_report._REPORTLAB_AVAILABLE = old_avail
    assert result == b"%PDF-1.4 report data"


def test_generate_no_library():
    with patch("shared.pdf_report._REPORTLAB_AVAILABLE", False), \
         patch("shared.pdf_report._FPDF2_AVAILABLE", False):
        result = generate_similarity_report_pdf(
            batch_name="Test",
            submission_a={},
            submission_b={},
            similarity_score=0.5,
            text_a="a",
            text_b="b",
        )
    assert result is None
