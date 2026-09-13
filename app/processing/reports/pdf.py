import io
from datetime import datetime, UTC
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def generate_forensic_pdf(
    job_id: str,
    overall_tlp: str,
    inspected_files: list[dict],
    timeline_events: list[dict],
    artifact_hash: str,
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#1e293b"),
    )
    section_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=12,
        spaceAfter=6,
    )
    cell_style = ParagraphStyle(
        "TableCell", parent=styles["Normal"], fontSize=9, leading=11
    )

    story = []

    # Title & Header
    story.append(Paragraph("<b>FORENSIC ANALYSIS REPORT</b>", title_style))
    story.append(Spacer(1, 10))

    meta_data = [
        [
            Paragraph("<b>Job ID:</b>", cell_style),
            Paragraph(job_id, cell_style),
            Paragraph("<b>Generated:</b>", cell_style),
            Paragraph(datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"), cell_style),
        ],
        [
            Paragraph("<b>TLP Rating:</b>", cell_style),
            Paragraph(f"<b>{overall_tlp}</b>", cell_style),
            Paragraph("<b>Integrity Hash:</b>", cell_style),
            Paragraph(f"{artifact_hash[:16]}...", cell_style),
        ],
    ]
    meta_table = Table(meta_data, colWidths=[80, 180, 80, 200])
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 15))

    # Evidence Inventory Table
    story.append(Paragraph("Evidence Inventory", section_style))
    inventory_data = [["Filename", "Category", "Inspection Status", "TLP Rating"]]
    for f in inspected_files:
        status = "Supported" if f.get("supported_for_inspection") else "Unsupported"
        inventory_data.append(
            [
                Paragraph(f.get("original_filename", ""), cell_style),
                Paragraph(f.get("media_category", ""), cell_style),
                Paragraph(status, cell_style),
                Paragraph(f.get("tlp_rating", "TLP:CLEAR"), cell_style),
            ]
        )

    inv_table = Table(inventory_data, colWidths=[180, 100, 140, 120])
    inv_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("PADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(inv_table)
    story.append(Spacer(1, 15))

    # Forensic Timeline Table
    story.append(Paragraph("Chronological Forensic Timeline", section_style))
    timeline_data = [["Timestamp", "Source File", "Event Detail"]]
    for event in timeline_events:
        timeline_data.append(
            [
                Paragraph(str(event.get("timestamp", "")), cell_style),
                Paragraph(str(event.get("source_file", "")), cell_style),
                Paragraph(str(event.get("event", "")), cell_style),
            ]
        )

    if len(timeline_data) == 1:
        timeline_data.append(
            [
                Paragraph("N/A", cell_style),
                Paragraph("N/A", cell_style),
                Paragraph("No temporal events extracted", cell_style),
            ]
        )

    time_table = Table(timeline_data, colWidths=[140, 140, 260])
    time_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#334155")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("PADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(time_table)

    doc.build(story)
    return buffer.getvalue()