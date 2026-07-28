"""Tests for OCR processor module."""
import os
import tempfile
from unittest.mock import MagicMock, patch

from shared.ocr_processor import is_ocr_needed, ocr_file


def test_is_ocr_needed_image():
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name
    try:
        assert is_ocr_needed(path) is True
    finally:
        os.unlink(path)


def test_is_ocr_needed_jpg():
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        path = f.name
    try:
        assert is_ocr_needed(path) is True
    finally:
        os.unlink(path)


def test_is_ocr_needed_txt():
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        path = f.name
    try:
        assert is_ocr_needed(path) is False
    finally:
        os.unlink(path)


def test_is_ocr_needed_scanned_pdf():
    with patch("pypdf.PdfReader") as mock_reader:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""
        mock_reader.return_value.pages = [mock_page, mock_page]
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name
        try:
            assert is_ocr_needed(path) is True
        finally:
            os.unlink(path)


def test_is_ocr_needed_text_pdf():
    with patch("pypdf.PdfReader") as mock_reader:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "A" * 100
        mock_reader.return_value.pages = [mock_page]
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name
        try:
            assert is_ocr_needed(path) is False
        finally:
            os.unlink(path)


def test_ocr_file_no_tesseract():
    with patch("shared.ocr_processor._TESSERACT_AVAILABLE", False):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            assert ocr_file(path) is None
        finally:
            os.unlink(path)


def test_ocr_file_image_success():
    import sys
    sys.modules['PIL'] = MagicMock()
    sys.modules['PIL.Image'] = MagicMock()

    import shared.ocr_processor
    old_tess = shared.ocr_processor._TESSERACT_AVAILABLE
    shared.ocr_processor._TESSERACT_AVAILABLE = True
    mock_tess = MagicMock()
    mock_tess.image_to_string.return_value = "OCR result"
    shared.ocr_processor.pytesseract = mock_tess
    mock_img_instance = MagicMock()
    sys.modules['PIL'].Image.open.return_value = mock_img_instance
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        try:
            result = ocr_file(path)
            assert result == "OCR result"
        finally:
            os.unlink(path)
    finally:
        shared.ocr_processor._TESSERACT_AVAILABLE = old_tess


def test_ocr_file_pdf_no_pdf2image():
    with patch("shared.ocr_processor._TESSERACT_AVAILABLE", True), \
         patch("shared.ocr_processor._PDF2IMAGE_AVAILABLE", False):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name
        try:
            assert ocr_file(path) is None
        finally:
            os.unlink(path)


def test_ocr_file_pdf_success():
    import shared.ocr_processor
    old_tess = shared.ocr_processor._TESSERACT_AVAILABLE
    old_pdf = shared.ocr_processor._PDF2IMAGE_AVAILABLE
    shared.ocr_processor._TESSERACT_AVAILABLE = True
    shared.ocr_processor._PDF2IMAGE_AVAILABLE = True
    mock_convert = MagicMock()
    mock_img = MagicMock()
    mock_convert.return_value = [mock_img]
    shared.ocr_processor.convert_from_path = mock_convert
    mock_tess = MagicMock()
    mock_tess.image_to_string.return_value = "PDF OCR text"
    shared.ocr_processor.pytesseract = mock_tess
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name
        try:
            result = ocr_file(path)
            assert result == "PDF OCR text"
        finally:
            os.unlink(path)
    finally:
        shared.ocr_processor._TESSERACT_AVAILABLE = old_tess
        shared.ocr_processor._PDF2IMAGE_AVAILABLE = old_pdf


def test_ocr_file_unsupported_ext():
    with patch("shared.ocr_processor._TESSERACT_AVAILABLE", True):
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            path = f.name
        try:
            assert ocr_file(path) is None
        finally:
            os.unlink(path)
