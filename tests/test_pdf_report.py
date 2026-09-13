from app.processing.reports.pdf import generate_forensic_pdf


def test_pdf_report_generation():
    pdf_bytes = generate_forensic_pdf(
        job_id="123e4567-e89b-12d3-a456-426614174000",
        overall_tlp="TLP:AMBER",
        inspected_files=[
            {
                "original_filename": "evidence.pdf",
                "media_category": "document",
                "supported_for_inspection": True,
                "tlp_rating": "TLP:AMBER",
            }
        ],
        timeline_events=[
            {
                "timestamp": "2026-09-13T04:30:00Z",
                "source_file": "evidence.pdf",
                "event": "File Created",
            }
        ],
        artifact_hash="a591a6d40bf420404a011733cfb7b190d62c65bf0bcda32b57b277d9ad9f146e",
    )

    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 500