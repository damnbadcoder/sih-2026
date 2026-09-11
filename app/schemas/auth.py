import uuid

from pydantic import BaseModel, EmailStr, Field, field_validator


def normalize_email(value: str) -> str:
    return value.strip().lower()


class SignupRequest(BaseModel):
    email: EmailStr = Field(..., description="Email must resolve to a valid address")
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return normalize_email(value)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return normalize_email(value)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreatedResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr