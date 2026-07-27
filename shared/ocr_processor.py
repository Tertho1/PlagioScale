import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_TESSERACT_AVAILABLE = False
try:
    import pytesseract

    _TESSERACT_AVAILABLE = True
except ImportError:
    logger.warning("pytesseract not installed — OCR disabled")

_PDF2IMAGE_AVAILABLE = False
try:
    from pdf2image import convert_from_path

    _PDF2IMAGE_AVAILABLE = True
except ImportError:
    logger.warning("pdf2image not installed — OCR for PDFs disabled")


_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp"}


def is_ocr_needed(file_path: str) -> bool:
    ext = Path(file_path).suffix.lower()
    if ext in _IMAGE_EXTS:
        return True
    if ext == ".pdf" and _is_scanned_pdf(file_path):
        return True
    return False


def _is_scanned_pdf(file_path: str) -> bool:
    try:
        import pypdf

        reader = pypdf.PdfReader(file_path)
        for page in reader.pages[:3]:
            text = page.extract_text()
            if text and len(text.strip()) > 50:
                return False
        return True
    except Exception:
        return False


def ocr_file(file_path: str, lang: str = "eng") -> Optional[str]:
    if not _TESSERACT_AVAILABLE:
        logger.warning("Tesseract not available — cannot OCR %s", file_path)
        return None

    ext = Path(file_path).suffix.lower()

    try:
        if ext == ".pdf":
            if not _PDF2IMAGE_AVAILABLE:
                logger.warning("pdf2image not available — cannot OCR PDF %s", file_path)
                return None
            images = convert_from_path(file_path, dpi=300)
            texts = []
            for img in images:
                text = pytesseract.image_to_string(img, lang=lang)
                texts.append(text)
            return "\n\n".join(texts)
        elif ext in _IMAGE_EXTS:
            from PIL import Image
            img = Image.open(file_path)
            return pytesseract.image_to_string(img, lang=lang)
        else:
            logger.warning("Unsupported file type for OCR: %s", ext)
            return None
    except Exception as e:
        logger.error("OCR failed for %s: %s", file_path, e)
        return None
