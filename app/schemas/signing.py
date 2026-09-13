# app/schemas/signing.py

from pydantic import BaseModel, Field


class VerifyRequest(BaseModel):
    content: str
    signature: str
    public_key: str


class VerifyResponse(BaseModel):
    is_authentic: bool
    message: str