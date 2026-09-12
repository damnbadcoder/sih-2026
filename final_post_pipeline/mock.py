from .types import FinalDeliverableResult, ProvenanceItem

def get_mock_final_deliverable(platform_key: str, approved_draft: str) -> FinalDeliverableResult:
    # A simple deterministic fallback
    mock_content = f"### Finalized Content for {platform_key}\n\nBased on the approved draft:\n{approved_draft}\n\nThis is a mock response because the API key is absent."
    
    return FinalDeliverableResult(
        platform_key=platform_key,
        final_content=mock_content,
        provenance=[
            ProvenanceItem(citation_marker="[^src-1]", source_reference="Mock Origin File")
        ]
    )
