from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class TimelineEvent(BaseModel):
    timestamp: datetime
    event_type: str
    source_file: str
    details: dict[str, Any] = Field(default_factory=dict)


def build_timeline(inspection_results: list[dict[str, Any]]) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []

    for item in inspection_results:
        filename = item.get("original_filename", "unknown")
        metadata = item.get("metadata", {})

        for key in ["created_at", "creation_date", "modified_at", "last_modified"]:
            if key in metadata and metadata[key]:
                val = metadata[key]
                dt = None
                if isinstance(val, datetime):
                    dt = val
                elif isinstance(val, str):
                    try:
                        dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                    except ValueError:
                        pass
                if dt:
                    events.append(
                        TimelineEvent(
                            timestamp=dt,
                            event_type=key,
                            source_file=filename,
                            details={"raw_value": str(val)},
                        )
                    )

    events.sort(key=lambda e: e.timestamp)
    return events