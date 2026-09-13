"""Renders a library reservation's acknowledgement slip as a PDF.

Kept separate from the agent/route layers -- this is a pure presentation
concern (bytes in, PDF bytes out) with no DB access of its own, so it's
easy to test in isolation and doesn't drag reportlab into agent logic.
"""
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (HRFlowable, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)


def render_slip_pdf(slip: dict) -> bytes:
    """`slip` is the dict returned by LibraryAgent.get_request_slip():
    request_id, slip_code, status, student_name, usn, book_title,
    book_author, requested_at, pickup_deadline."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A5, topMargin=16 * mm, bottomMargin=16 * mm,
                            leftMargin=14 * mm, rightMargin=14 * mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("SlipTitle", parent=styles["Title"], fontSize=15,
                                 spaceAfter=2)
    sub_style = ParagraphStyle("SlipSub", parent=styles["Normal"], fontSize=9,
                               textColor=colors.HexColor("#555555"))
    label_style = ParagraphStyle("Label", parent=styles["Normal"], fontSize=8,
                                 textColor=colors.HexColor("#777777"))
    value_style = ParagraphStyle("Value", parent=styles["Normal"], fontSize=11)
    code_style = ParagraphStyle("Code", parent=styles["Normal"], fontSize=30,
                                fontName="Courier-Bold", alignment=1,
                                textColor=colors.HexColor("#16283c"),
                                letterSpacing=6)
    note_style = ParagraphStyle("Note", parent=styles["Normal"], fontSize=8.5,
                                textColor=colors.HexColor("#555555"))

    story = [
        Paragraph("Library Book Reservation Slip", title_style),
        Paragraph("Mangalore Institute of Technology &amp; Engineering "
                  "&middot; MAWOS Library Agent", sub_style),
        Spacer(1, 10),
        HRFlowable(width="100%", color=colors.HexColor("#b08b2e"), thickness=1.2),
        Spacer(1, 10),
    ]

    def row(label, value):
        return [Paragraph(label, label_style), Paragraph(str(value), value_style)]

    table_data = [
        row("REQUEST ID", f"#{slip['request_id']}"),
        row("STUDENT", f"{slip['student_name']} ({slip['usn']})"),
        row("BOOK", slip.get("book_title") or "-"),
        row("AUTHOR", slip.get("book_author") or "-"),
        row("REQUESTED AT", str(slip["requested_at"])[:16]),
        row("PICKUP DEADLINE", str(slip["pickup_deadline"])[:16]),
        row("STATUS", slip["status"].upper()),
    ]
    t = Table(table_data, colWidths=[42 * mm, 95 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(t)
    story.append(Spacer(1, 14))

    story.append(Paragraph("VERIFICATION CODE", label_style))
    story.append(Spacer(1, 4))
    code_box = Table([[Paragraph(slip["slip_code"] or "------", code_style)]],
                     colWidths=[137 * mm])
    code_box.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.2, colors.HexColor("#16283c")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f3e6c4")),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(code_box)
    story.append(Spacer(1, 14))

    story.append(HRFlowable(width="100%", color=colors.HexColor("#dddddd"), thickness=0.6))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Show this slip (screen or printout) to the librarian to collect your book. "
        "The librarian will verify the 6-digit code above before handing over the "
        "book. This slip is valid only until the pickup deadline; after that the "
        "reservation expires automatically and a fine applies.", note_style))

    doc.build(story)
    return buf.getvalue()
