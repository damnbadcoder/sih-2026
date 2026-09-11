from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    SignupRequest,
    TokenResponse,
    UserCreatedResponse,
    UserProfileResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])

CONFLICT = status.HTTP_409_CONFLICT
UNAUTHORIZED = status.HTTP_401_UNAUTHORIZED
FORBIDDEN = status.HTTP_403_FORBIDDEN


def _profile(user: User) -> UserProfileResponse:
    user_type = user.user_type if user.user_type is not None else None
    return UserProfileResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        user_type=user_type,
        organisation=user.organisation,
    )


async def _register_user(
    db: AsyncSession, payload: RegisterRequest
) -> UserCreatedResponse:
    existing = await db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(CONFLICT, detail="An account with this email already exists")

    user = User(email=payload.email, password_hash=hash_password(payload.password))
    user.name = payload.name
    user.user_type = payload.user_type.value if payload.user_type is not None else None
    user.organisation = payload.organisation
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(CONFLICT, detail="An account with this email already exists") from None
    await db.refresh(user)

    return UserCreatedResponse(**_profile(user).model_dump())


@router.post("/register", response_model=UserCreatedResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest, db: AsyncSession = Depends(get_db)
) -> UserCreatedResponse:
    return await _register_user(db, payload)


@router.post("/signup", response_model=UserCreatedResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest, db: AsyncSession = Depends(get_db)) -> UserCreatedResponse:
    return await _register_user(db, payload)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    user = await db.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(UNAUTHORIZED, detail="Incorrect email or password")

    if not user.is_active:
        raise HTTPException(FORBIDDEN, detail="Account is inactive")

    token = create_access_token(
        subject=str(user.id),
        user_type=user.user_type,
    )
    return TokenResponse(access_token=token, token_type="bearer", user=_profile(user))