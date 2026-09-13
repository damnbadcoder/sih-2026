# app/api/v1/endpoints/signing.py

from fastapi import APIRouter
from app.services.signing import SigningService
from app.schemas.signing import VerifyRequest, VerifyResponse

router = APIRouter(prefix="/deliverables", tags=["Deliverables Signing"])


@router.post("/verify", response_model=VerifyResponse)
async def verify_deliverable_signature(payload: VerifyRequest):
    content_bytes = payload.content.encode("utf-8")
    valid = SigningService.verify_signature(
        public_key_b64=payload.public_key,
        content=content_bytes,
        signature_b64=payload.signature,
    )
    if valid:
        return VerifyResponse(
            is_authentic=True,
            message="Authentic, unmodified deliverable signature verified.",
        )
    return VerifyResponse(
        is_authentic=False,
        message="Tampered or forged signature detected.",
    )