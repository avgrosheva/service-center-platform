"""
Unit tests for the pure PDF renderer (Milestone 14): app.documents.job_report.

No DB, no S3, no background task — just JobReportData in, PDF bytes out.
This is exactly the roadmap's first testing-checklist item: "manually
calling the rendering function (outside the background task) produces a
correct, readable PDF from sample job data." pypdf reads the generated
bytes back and asserts on the actual extracted text, not just "a
non-empty PDF was produced" — per the explicit instruction not to settle
for a file-existence check here.
"""

import io
from datetime import date, datetime, timezone
from decimal import Decimal

from pypdf import PdfReader

from app.documents.job_report import JobReportData, MaterialLine, render_job_report_pdf


def _extract_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() for page in reader.pages)


def _sample_data(**overrides) -> JobReportData:
    defaults = dict(
        job_id="11111111-1111-1111-1111-111111111111",
        document_type="job_report",
        customer_name="Anna Ivanova",
        address="5 Pushkina St, Apt 12",
        status="completed",
        reported_issue="AC unit blowing warm air, compressor making noise",
        generated_at=datetime(2026, 3, 15, 12, 0, tzinfo=timezone.utc),
        equipment_description=None,
        technician_name=None,
        materials=[],
        work_notes=[],
        is_warranty_claim=False,
        warranty_expires_at=None,
    )
    defaults.update(overrides)
    return JobReportData(**defaults)


def test_render_produces_a_valid_pdf_with_a_single_page():
    pdf_bytes = render_job_report_pdf(_sample_data())

    assert pdf_bytes.startswith(b"%PDF")
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) == 1


def test_rendered_content_includes_core_job_fields():
    data = _sample_data(
        customer_name="Anna Ivanova",
        address="5 Pushkina St, Apt 12",
        reported_issue="AC unit blowing warm air, compressor making noise",
        technician_name="Sergey Volkov",
        status="completed",
    )

    text = _extract_text(render_job_report_pdf(data))

    assert "Anna Ivanova" in text
    assert "5 Pushkina St, Apt 12" in text
    assert "AC unit blowing warm air, compressor making noise" in text
    assert "Sergey Volkov" in text
    assert "completed" in text
    assert data.job_id in text


def test_rendered_content_includes_materials_table():
    data = _sample_data(
        materials=[
            MaterialLine(name="Refrigerant R410A", quantity=Decimal("2.5"), unit_cost=Decimal("1500.00")),
            MaterialLine(name="Compressor relay", quantity=Decimal("1"), unit_cost=None),
        ]
    )

    text = _extract_text(render_job_report_pdf(data))

    assert "Materials Used" in text
    assert "Refrigerant R410A" in text
    assert "2.5" in text
    assert "1500.00" in text
    assert "Compressor relay" in text


def test_rendered_content_includes_work_notes_from_timeline():
    data = _sample_data(work_notes=["Assigned to Sergey Volkov", "Replaced compressor relay"])

    text = _extract_text(render_job_report_pdf(data))

    assert "Work Performed" in text
    assert "Assigned to Sergey Volkov" in text
    assert "Replaced compressor relay" in text


def test_rendered_content_reflects_warranty_terms_when_present():
    data = _sample_data(is_warranty_claim=True, warranty_expires_at=date(2026, 6, 1))

    text = _extract_text(render_job_report_pdf(data))

    assert "warranty claim" in text.lower()
    assert "2026-06-01" in text


def test_rendered_content_shows_no_warranty_when_absent():
    data = _sample_data(is_warranty_claim=False, warranty_expires_at=None)

    text = _extract_text(render_job_report_pdf(data))

    assert "No warranty period set." in text
    assert "warranty claim" not in text.lower()


def test_repair_certificate_uses_a_different_title_than_job_report():
    job_report_text = _extract_text(render_job_report_pdf(_sample_data(document_type="job_report")))
    certificate_text = _extract_text(render_job_report_pdf(_sample_data(document_type="repair_certificate")))

    assert "Job Report" in job_report_text
    assert "Repair Certificate" in certificate_text
    assert "Repair Certificate" not in job_report_text


def test_unassigned_technician_is_labeled_explicitly():
    data = _sample_data(technician_name=None)

    text = _extract_text(render_job_report_pdf(data))

    assert "Unassigned" in text
