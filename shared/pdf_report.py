import io
import logging
import os
import tempfile
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

_REPORTLAB_AVAILABLE = False
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch, mm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
        PageBreak,
    )

    _REPORTLAB_AVAILABLE = True
except ImportError:
    logger.warning("reportlab not available — PDF generation disabled")

_FPDF2_AVAILABLE = False
try:
    import fpdf

    _FPDF2_AVAILABLE = True
except ImportError:
    logger.warning("fpdf2 not available — trying reportlab")


def _highlight_diff_words(text_a: str, text_b: str) -> Tuple[List[str], List[str]]:
    words_a = text_a.split()
    words_b = text_b.split()
    set_b = set(words_b)
    set_a = set(words_a)
    highlighted_a = []
    highlighted_b = []
    for w in words_a:
        highlighted_a.append(f"<b>{w}</b>" if w in set_b else w)
    for w in words_b:
        highlighted_b.append(f"<b>{w}</b>" if w in set_a else w)
    return highlighted_a, highlighted_b


def generate_similarity_report_pdf(
    batch_name: str,
    submission_a: dict,
    submission_b: dict,
    similarity_score: float,
    text_a: str,
    text_b: str,
    ai_score_a: Optional[float] = None,
    ai_score_b: Optional[float] = None,
    output_path: Optional[str] = None,
) -> Optional[bytes]:
    if _REPORTLAB_AVAILABLE:
        return _generate_reportlab(
            batch_name, submission_a, submission_b, similarity_score,
            text_a, text_b, ai_score_a, ai_score_b, output_path,
        )
    if _FPDF2_AVAILABLE:
        return _generate_fpdf2(
            batch_name, submission_a, submission_b, similarity_score,
            text_a, text_b, ai_score_a, ai_score_b, output_path,
        )
    logger.error("No PDF library available — install reportlab or fpdf2")
    return None


def _generate_reportlab(
    batch_name: str,
    sub_a: dict,
    sub_b: dict,
    score: float,
    text_a: str,
    text_b: str,
    ai_a: Optional[float],
    ai_b: Optional[float],
    output_path: Optional[str],
) -> Optional[bytes]:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        output_path or buf,
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    hl_style = ParagraphStyle("Highlighted", parent=styles["Normal"], textColor=colors.red)

    elements = []
    elements.append(Paragraph(f"Plagiarism Report — {batch_name}", styles["Title"]))
    elements.append(Spacer(1, 12))
    elements.append(
        Paragraph(
            f"<b>Similarity Score: {score:.1%}</b>",
            styles["Heading2"],
        )
    )
    elements.append(Spacer(1, 12))

    info_data = [
        ["", "Submission A", "Submission B"],
        ["Roll", sub_a.get("roll", "—"), sub_b.get("roll", "—")],
        ["Name", sub_a.get("name", "—"), sub_b.get("name", "—")],
    ]
    if ai_a is not None or ai_b is not None:
        info_data.append([
            "AI Score",
            f"{ai_a:.1%}" if ai_a is not None else "—",
            f"{ai_b:.1%}" if ai_b is not None else "—",
        ])
    info_table = Table(info_data)
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ]))
    elements.append(info_table)
    elements.append(PageBreak())

    elements.append(Paragraph("Text Comparison", styles["Heading2"]))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph("<b>Submission A — Highlighted Matches</b>", styles["Heading3"]))
    words_a_hl, _ = _highlight_diff_words(text_a, text_b)
    elements.append(Paragraph(" ".join(words_a_hl), hl_style))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph("<b>Submission B — Highlighted Matches</b>", styles["Heading3"]))
    _, words_b_hl = _highlight_diff_words(text_a, text_b)
    elements.append(Paragraph(" ".join(words_b_hl), hl_style))

    doc.build(elements)
    if output_path:
        return None
    return buf.getvalue()


def _generate_fpdf2(
    batch_name: str,
    sub_a: dict,
    sub_b: dict,
    score: float,
    text_a: str,
    text_b: str,
    ai_a: Optional[float],
    ai_b: Optional[float],
    output_path: Optional[str],
) -> Optional[bytes]:
    pdf = fpdf.FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, f"Plagiarism Report - {batch_name}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 10, f"Similarity Score: {score:.1%}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 8, f"Submission A: {sub_a.get('roll', '—')} - {sub_a.get('name', '—')}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Submission B: {sub_b.get('roll', '—')} - {sub_b.get('name', '—')}", new_x="LMARGIN", new_y="NEXT")
    if ai_a is not None:
        pdf.cell(0, 8, f"AI Score A: {ai_a:.1%}", new_x="LMARGIN", new_y="NEXT")
    if ai_b is not None:
        pdf.cell(0, 8, f"AI Score B: {ai_b:.1%}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, "Text Comparison", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    words_a_hl, _ = _highlight_diff_words(text_a, text_b)
    pdf.multi_cell(0, 5, " ".join(words_a_hl))
    pdf.ln(6)
    pdf.multi_cell(0, 5, " ".join(words_a_hl))

    if output_path:
        pdf.output(output_path)
        return None
    return pdf.output()
