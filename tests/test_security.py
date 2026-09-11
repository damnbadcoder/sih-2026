from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.config import get_settings
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

settings = get_settings()


def test_password_hash_not_plaintext():
    hashed = hash_password("supersecret")
    assert hashed != "supersecret"
    assert "supersecret" not in hashed


def test_password_hash_starts_with_bcrypt_prefix():
    assert hash_password("supersecret").startswith("$2")


def test_verify_correct_password():
    hashed = hash_password("supersecret")
    assert verify_password("supersecret", hashed) is True


def test_verify_incorrect_password():
    hashed = hash_password("supersecret")
    assert verify_password("wrongpassword", hashed) is False


def test_jwt_create_and_decode_roundtrip():
    token = create_access_token(subject="user-123")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-123"
    assert "exp" in payload


def test_jwt_hashing_is_unique():
    assert hash_password("same") != hash_password("same")


def test_expired_jwt_rejected():
    now = datetime.now(UTC)
    payload = {"sub": "user-123", "iat": now, "exp": now - timedelta(minutes=1)}
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_malformed_jwt_rejected():
    with pytest.raises(InvalidTokenError):
        decode_access_token("this.is.not.a.jwt")


def test_algorithm_confusion_rejected():
    payload = {"sub": "user-123", "exp": datetime.now(UTC) + timedelta(minutes=5)}
    token = jwt.encode(payload, "not-the-secret", algorithm="HS256")
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_none_algorithm_rejected():
    now = datetime.now(UTC)
    payload = {"sub": "user-123", "iat": now, "exp": now + timedelta(minutes=5)}
    token = jwt.encode(payload, key=None, algorithm="none")
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_token_missing_subject_rejected():
    now = datetime.now(UTC)
    payload = {"iat": now, "exp": now + timedelta(minutes=5)}
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)