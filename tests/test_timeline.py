from datetime import datetime, timezone
import pytest
from app.processing.timeline import build_timeline


def test_timeline_sorting_and_parsing():
    mock_results = [
        {
            "original_filename": "evidence2.pdf",
            "metadata": {"created_at": "2026-09-12T10:00:00Z"},
        },
        {
            "original_filename": "evidence1.docx",
            "metadata": {"created_at": "2026-09-10T08:30:00Z"},
        },
    ]

    events = build_timeline(mock_results)

    assert len(events) == 2
    assert events[0].source_file == "evidence1.docx"
    assert events[1].source_file == "evidence2.pdf"
    assert events[0].timestamp < events[1].timestamp


def test_timeline_empty_metadata():
    events = build_timeline([{"original_filename": "test.txt", "metadata": {}}])
    assert events == []