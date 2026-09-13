# app/api/v1/endpoints/sharing.py

from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.schemas.sharing import ShareLinkCreate, ShareLinkResponse
from app.services.sharing import SharingService

router = APIRouter(tags=["Transformation Sharing"])


async def get_db():
    async with async_session_factory() as session:
        yield session


@router.post("/transformations/{transformation_id}/share", response_model=ShareLinkResponse)
async def create_share_link(
    transformation_id: UUID,
    payload: ShareLinkCreate,
    current_user_id: UUID = Query(...),
    tenant_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    try:
        link = await SharingService.create_share_link(
            db=db,
            transformation_id=transformation_id,
            user_id=current_user_id,
            tenant_id=tenant_id,
            permission=payload.permission,
            expires_at=payload.expires_at,
            max_uses=payload.max_uses,
            requires_auth=payload.requires_auth,
            recipient_email=payload.recipient_email,
        )
        return link
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/share/resolve/{token}", response_model=ShareLinkResponse)
async def resolve_share_link(
    token: str,
    user_email: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    try:
        link = await SharingService.resolve_share_link(db, token, user_email)
        return link
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete("/share/{link_id}", status_code=204)
async def revoke_share_link(
    link_id: UUID,
    current_user_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    success = await SharingService.revoke_link(db, link_id, current_user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Share link not found or unauthorized.")
    return None