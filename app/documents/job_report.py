"""
Job report / repair certificate PDF rendering (Milestone 14).

Pure rendering: takes already-loaded data (never touches the database or
S3 itself) and returns PDF bytes. This separation is what the roadmap's
own testing checklist asks for directly — "manually calling the rendering
function (outside the background task) produces a correct, readable PDF
from sample job data" is only a meaningful, fast, isolated test because
this function has no I/O dependencies of its own.

Kept deliberately plain per the roadmap ("keep the template intentionally
plain for MVP — no need for polished design work here"): reportlab's basic
flowables (Paragraph, Table, Spacer), the sample stylesheet, no custom
fonts or branding.
"""

import io
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


@dataclass
class MaterialLine:
    name: str
    quantity: Decimal
    unit_cost: Decimal | None


@dataclass
class JobReportData:
    """
    Everything the template needs, and nothing it has to go fetch itself.
    Field set matches the roadmap's PDF content list exactly: reported
    issue, work done (from timeline/notes), materials used, technician
    name, warranty terms — no additional-work or payment data, since
    those aren't in that list.
    """

    job_id: str
    document_type: str  # "job_report" or "repair_certificate" — controls only the title
    customer_name: str
    address: str
    status: str
    reported_issue: str
    generated_at: datetime
    equipment_description: str | None = None
    technician_name: str | None = None
    materials: list[MaterialLine] = field(default_factory=list)
    work_notes: list[str] = field(default_factory=list)
    is_warranty_claim: bool = False
    warranty_expires_at: date | None = None


def render_job_report_pdf(data: JobReportData) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm)
    styles = getSampleStyleSheet()
    story = []

    title = "Repair Certificate" if data.document_type == "repair_certificate" else "Job Report"
    story.append(Paragraph(title, styles["Title"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph(f"Job ID: {data.job_id}", styles["Normal"]))
    story.append(Paragraph(f"Status: {data.status}", styles["Normal"]))
    story.append(Paragraph(f"Customer: {data.customer_name}", styles["Normal"]))
    story.append(Paragraph(f"Address: {data.address}", styles["Normal"]))
    if data.equipment_description:
        story.append(Paragraph(f"Equipment: {data.equipment_description}", styles["Normal"]))
    story.append(Paragraph(f"Technician: {data.technician_name or 'Unassigned'}", styles["Normal"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("Reported Issue", styles["Heading2"]))
    story.append(Paragraph(data.reported_issue, styles["Normal"]))
    story.append(Spacer(1, 12))

    if data.work_notes:
        story.append(Paragraph("Work Performed", styles["Heading2"]))
        for note in data.work_notes:
            story.append(Paragraph(f"- {note}", styles["Normal"]))
        story.append(Spacer(1, 12))

    if data.materials:
        story.append(Paragraph("Materials Used", styles["Heading2"]))
        table_data = [["Name", "Quantity", "Unit Cost"]]
        for material in data.materials:
            unit_cost = str(material.unit_cost) if material.unit_cost is not None else "-"
            table_data.append([material.name, str(material.quantity), unit_cost])
        table = Table(table_data, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 12))

    story.append(Paragraph("Warranty", styles["Heading2"]))
    if data.is_warranty_claim:
        story.append(Paragraph("This job is a warranty claim.", styles["Normal"]))
    if data.warranty_expires_at:
        story.append(Paragraph(f"Warranty valid until: {data.warranty_expires_at.isoformat()}", styles["Normal"]))
    else:
        story.append(Paragraph("No warranty period set.", styles["Normal"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph(f"Generated: {data.generated_at.isoformat()}", styles["Normal"]))

    doc.build(story)
    return buffer.getvalue()
