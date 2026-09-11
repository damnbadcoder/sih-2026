from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET_PLACEHOLDER = "dev-secret-change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "SIH 2026 GenAI Platform"
    APP_ENV: str = "development"
    DEBUG: bool = True

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/sih_genai"

    JWT_SECRET_KEY: str = DEV_JWT_SECRET_PLACEHOLDER
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_BYTES: int = 25 * 1024 * 1024

    @model_validator(mode="after")
    def _validate_jwt_secret(self) -> "Settings":
        if self.APP_ENV != "production":
            return self
        if (
            not self.JWT_SECRET_KEY.strip()
            or len(self.JWT_SECRET_KEY) < 32
            or self.JWT_SECRET_KEY == DEV_JWT_SECRET_PLACEHOLDER
        ):
            raise ValueError(
                "JWT_SECRET_KEY must be a strong secret of at least 32 characters; "
                "the development placeholder is not allowed in production"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()