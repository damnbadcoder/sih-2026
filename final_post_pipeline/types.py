from pydantic import BaseModel, Field
from typing import List, Dict, Any

class ProvenanceItem(BaseModel):
    citation_marker: str
    source_reference: str

class FinalDeliverableResult(BaseModel):
    platform_key: str
    final_content: str
    provenance: List[ProvenanceItem] = Field(default_factory=list)
