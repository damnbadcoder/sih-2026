import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.user_types import UserType


def normalize_email(value: str) -> str:
    return value.strip().lower()


class RegisterRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr = Field(..., description="Email must resolve to a valid address")
    password: str = Field(min_length=8, max_length=128)
    user_type: UserType | None = None
    organisation: str | None = Field(default=None, max_length=255)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("name", "organisation")
    @classmethod
    def _strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()


class SignupRequest(RegisterRequest):
    """Backwards-compatible alias of ``RegisterRequest``.

    ``POST /auth/signup`` and ``POST /auth/register`` use identical
    behaviour and validation.
    """


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return normalize_email(value)


class UserProfileResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    name: str | None = None
    user_type: str | None = None
    organisation: str | None = None


class UserCreatedResponse(UserProfileResponse):
    pass


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfileResponse