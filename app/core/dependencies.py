import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.storage import get_storage  # <-- Added storage dependency export

bearer_scheme = HTTPBearer(auto_error=False)

UNAUTHORIZED = status.HTTP_401_UNAUTHORIZED


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(UNAUTHORIZED, detail="Not authenticated")

    try:
        payload = decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise HTTPException(UNAUTHORIZED, detail="Invalid or expired token") from None

    subject = payload.get("sub")
    try:
        user_id = uuid.UUID(subject)
    except (ValueError, TypeError):
        raise HTTPException(UNAUTHORIZED, detail="Invalid token") from None

    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        raise HTTPException(UNAUTHORIZED, detail="Invalid or expired token")

    return user