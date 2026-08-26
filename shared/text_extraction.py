"""Text extraction from common document formats."""
import tempfile
from pathlib import Path


def extract_text(file_path: str) -> str:
    suffix = Path(file_path).suffix.lower()
    try:
        if suffix in {".txt", ".md", ".csv", ".py", ".java", ".js", ".ts"}:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        if suffix == ".pdf":
            from pypdf import PdfReader
            with open(file_path, "rb") as fh:
                reader = PdfReader(fh)
                parts = []
                for page in reader.pages:
                    parts.append(page.extract_text() or "")
                return "\n".join(parts)
        if suffix == ".docx":
            from docx import Document
            doc = Document(file_path)
            text = "\n".join(p.text for p in doc.paragraphs)
            return text
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        return f"ERROR: {str(e)}"


def extract_text_from_bytes(content: bytes, filename: str) -> str:
    """Extract text from in-memory file content.

    Writes to a temp file so the format-specific extractors can be reused.
    """
    suffix = Path(filename).suffix.lower()
    tmp = None
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        tmp.write(content)
        tmp.close()
        return extract_text(tmp.name)
    finally:
        if tmp is not None:
            try:
                Path(tmp.name).unlink(missing_ok=True)
            except OSError:
                pass
