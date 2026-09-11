import pytest
from pydantic import ValidationError

from app.config import DEV_JWT_SECRET_PLACEHOLDER, Settings


def test_development_accepts_placeholder():
    settings = Settings(APP_ENV="development", JWT_SECRET_KEY=DEV_JWT_SECRET_PLACEHOLDER)
    assert settings.JWT_SECRET_KEY == DEV_JWT_SECRET_PLACEHOLDER


def test_production_rejects_placeholder():
    with pytest.raises(ValidationError):
        Settings(APP_ENV="production", JWT_SECRET_KEY=DEV_JWT_SECRET_PLACEHOLDER)


def test_production_rejects_empty_secret():
    with pytest.raises(ValidationError):
        Settings(APP_ENV="production", JWT_SECRET_KEY="")


def test_production_rejects_short_secret():
    with pytest.raises(ValidationError):
        Settings(APP_ENV="production", JWT_SECRET_KEY="short")


def test_production_accepts_long_non_placeholder_secret():
    secret = "a" * 64
    settings = Settings(APP_ENV="production", JWT_SECRET_KEY=secret)
    assert secret == settings.JWT_SECRET_KEY