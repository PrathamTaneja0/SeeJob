"""Markdown to ATS-friendly PDF export."""

from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_BULLET_RE = re.compile(r"^[-*]\s+(.+)$")


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=16,
            spaceAfter=10,
            alignment=TA_LEFT,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            spaceBefore=8,
            spaceAfter=6,
            alignment=TA_LEFT,
        ),
        "h3": ParagraphStyle(
            "H3",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=11,
            spaceBefore=6,
            spaceAfter=4,
            alignment=TA_LEFT,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            spaceAfter=6,
            alignment=TA_LEFT,
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            leftIndent=18,
            spaceAfter=4,
            alignment=TA_LEFT,
        ),
    }


def markdown_to_pdf(markdown_content: str, output_path: Path) -> Path:
    """Compile Markdown to a single-column, ATS-friendly PDF.

    Uses standard Helvetica fonts with no tables or graphics.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    styles = _build_styles()
    story: list = []

    for raw_line in markdown_content.splitlines():
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 0.08 * inch))
            continue

        heading_match = _HEADING_RE.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            text = _escape_xml(heading_match.group(2))
            style_key = "h1" if level == 1 else "h2" if level == 2 else "h3"
            story.append(Paragraph(text, styles[style_key]))
            continue

        bullet_match = _BULLET_RE.match(line)
        if bullet_match:
            text = _escape_xml(bullet_match.group(1))
            story.append(Paragraph(f"&bull; {text}", styles["bullet"]))
            continue

        story.append(Paragraph(_escape_xml(line), styles["body"]))

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    doc.build(story)
    return output_path
