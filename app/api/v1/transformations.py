import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.grounding import GroundingContext
from app.schemas.transformation import (
    TransformationCreateRequest,
    TransformationResponse,
)
from app.services.errors import NotFoundError, ServiceError
from app.services.grounding import GroundingService
from app.services.transformations import TransformationService

router = APIRouter(prefix="/transformations", tags=["transformations"])

NOT_FOUND = status.HTTP_404_NOT_FOUND


def _not_found(exc: ServiceError) -> HTTPException:
    return HTTPException(NOT_FOUND, detail=str(exc))


@router.post(
    "",
    response_model=TransformationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_transformation(
    payload: TransformationCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TransformationResponse:
    service = TransformationService()
    try:
        transformation = await service.create_transformation(db, current_user, payload)
    except NotFoundError as exc:
        raise _not_found(exc) from None
    except ServiceError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from None
    return TransformationResponse.model_validate(transformation)


@router.get("", response_model=list[TransformationResponse])
async def list_transformations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[TransformationResponse]:
    service = TransformationService()
    transformations = await service.list_for_user(db, current_user)
    return [TransformationResponse.model_validate(item) for item in transformations]


@router.get("/{transformation_id}", response_model=TransformationResponse)
async def get_transformation(
    transformation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TransformationResponse:
    service = TransformationService()
    try:
        transformation = await service.get_for_user(db, current_user, transformation_id)
    except NotFoundError as exc:
        raise _not_found(exc) from None
    return TransformationResponse.model_validate(transformation)


@router.get("/{transformation_id}/grounding", response_model=GroundingContext)
async def get_transformation_grounding(
    transformation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GroundingContext:
    service = TransformationService()
    try:
        transformation = await service.get_for_user(db, current_user, transformation_id)
    except NotFoundError as exc:
        raise _not_found(exc) from None
    return await GroundingService().build_context(transformation)