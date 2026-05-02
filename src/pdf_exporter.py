"""
PDF report generator using ReportLab.

Generates a consolidated blood test history with:
  - Rows: exam names
  - Columns: exam dates (sorted chronologically)
  - Cell values: measured result
"""

from pathlib import Path
from datetime import datetime

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from src.aggregator import pivot_table


HEADER_COLOR = colors.HexColor("#1a6ba0")
ALT_ROW_COLOR = colors.HexColor("#eaf3fb")
BORDER_COLOR = colors.HexColor("#aaccee")
TEXT_COLOR = colors.HexColor("#1a1a1a")


def _build_pdf(df: pd.DataFrame, dest) -> None:
    """Build PDF content and write to dest (file path string or BytesIO)."""
    pivot = pivot_table(df)

    doc = SimpleDocTemplate(
        dest,
        pagesize=landscape(A4),
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        fontSize=16,
        textColor=HEADER_COLOR,
        alignment=TA_CENTER,
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.grey,
        alignment=TA_CENTER,
        spaceAfter=12,
    )
    cell_style = ParagraphStyle(
        "Cell",
        parent=styles["Normal"],
        fontSize=7,
        leading=9,
    )

    story = []

    # Title
    story.append(Paragraph("Histórico Consolidado de Exames de Sangue", title_style))
    story.append(Paragraph(
        f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} · "
        f"{len(pivot)} exames · {len(pivot.columns)} datas",
        subtitle_style,
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=HEADER_COLOR))
    story.append(Spacer(1, 0.4 * cm))

    if pivot.empty:
        story.append(Paragraph("Nenhum dado encontrado.", styles["Normal"]))
        doc.build(story)
        return

    # Build table data
    date_cols = list(pivot.columns)
    header_row = ["Exame"] + date_cols
    data = [header_row]

    for exam_name, row in pivot.iterrows():
        row_data = [str(exam_name)]
        for col in date_cols:
            val = row.get(col, "")
            row_data.append("" if pd.isna(val) else str(val))
        data.append(row_data)

    # Column widths: fixed for exam name, equal for dates
    page_width = landscape(A4)[0] - 3 * cm
    exam_col_width = 5 * cm
    remaining = page_width - exam_col_width
    date_col_width = min(remaining / max(len(date_cols), 1), 2.2 * cm)

    col_widths = [exam_col_width] + [date_col_width] * len(date_cols)

    table = Table(data, colWidths=col_widths, repeatRows=1)

    # Table styling
    style_commands = [
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_COLOR),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ALT_ROW_COLOR]),
        # Data cells
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, -1), 7),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("VALIGN", (0, 1), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER_COLOR),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    table.setStyle(TableStyle(style_commands))

    story.append(table)

    # Labs summary
    story.append(Spacer(1, 0.5 * cm))
    labs = df["lab"].unique()
    labs_str = " · ".join(sorted(labs))
    story.append(Paragraph(
        f"<font size='8' color='grey'>Laboratórios: {labs_str}</font>",
        styles["Normal"],
    ))

    doc.build(story)


def generate_pdf_bytes(df: pd.DataFrame) -> bytes:
    """
    Generate a consolidated PDF report entirely in memory.

    Returns:
        PDF content as bytes — never written to disk.
    """
    import io
    buf = io.BytesIO()
    _build_pdf(df, buf)
    return buf.getvalue()


def generate_pdf_report(df: pd.DataFrame, output_path: str | Path) -> Path:
    """
    Generate a consolidated PDF report saved to disk.

    Args:
        df: The aggregated DataFrame from aggregator.build_dataframe()
        output_path: Where to save the PDF

    Returns:
        Path to the generated PDF
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _build_pdf(df, str(output_path))
    return output_path
