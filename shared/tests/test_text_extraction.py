"""Tests for text extraction from common document formats."""
import tempfile
import os
from unittest.mock import patch, MagicMock
from shared.text_extraction import extract_text


def test_extract_txt():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("Hello world")
        path = f.name
    try:
        assert extract_text(path) == "Hello world"
    finally:
        os.unlink(path)


def test_extract_md():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("# Title\nBody")
        path = f.name
    try:
        assert "# Title\nBody" in extract_text(path)
    finally:
        os.unlink(path)


def test_extract_pdf():
    text = "PDF extracted text"
    with patch("pypdf.PdfReader") as mock_reader:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = text
        mock_reader.return_value.pages = [mock_page]

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 dummy")
            path = f.name
        try:
            result = extract_text(path)
            assert text in result
        finally:
            os.unlink(path)


def test_extract_docx():
    with patch("docx.Document") as mock_doc:
        mock_para = MagicMock()
        mock_para.text = "DOCX text"
        mock_doc.return_value.paragraphs = [mock_para]

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(b"dummy docx")
            path = f.name
        try:
            assert extract_text(path) == "DOCX text"
        finally:
            os.unlink(path)


def test_extract_error_handling():
    result = extract_text("/nonexistent/file.txt")
    assert result.startswith("ERROR:")


def test_extract_empty_txt():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        path = f.name
    try:
        assert extract_text(path) == ""
    finally:
        os.unlink(path)


def test_extract_unknown_suffix():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xyz", delete=False) as f:
        f.write("fallback read")
        path = f.name
    try:
        assert extract_text(path) == "fallback read"
    finally:
        os.unlink(path)
