"""
Centralized application configuration.

All configuration is sourced from environment variables (optionally loaded
from a local .env file in development). No secrets are hardcoded here -
this module only defines names, types, and safe defaults for non-sensitive
values such as timeouts and pagination limits.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings loaded from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- General ---
    APP_NAME: str = "Clinic Booking API"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: Literal["development", "test", "staging", "production"] = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # --- Database ---
    # Example: postgresql+asyncpg://user:password@host:5432/dbname
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/clinic_booking",
        description="Async SQLAlchemy connection string for the primary database.",
    )
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 5
    DATABASE_ECHO: bool = False

    # --- CORS ---
    CORS_ALLOWED_ORIGINS: list[str] = Field(default_factory=lambda: ["*"])
    CORS_ALLOW_CREDENTIALS: bool = True

    # --- Business rules ---
    SLOT_DURATION_MINUTES: int = 30
    MIN_BOOKING_LEAD_MINUTES: int = 60  # bonus rule: no booking within 1 hour of "now"

    # --- Logging ---
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    LOG_JSON: bool = True

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        """Ensure the driver is the async psycopg/asyncpg variant, not a sync one."""
        if value.startswith("postgresql://"):
            # Common mistake: sync driver string supplied by hosting provider (e.g. Render).
            # We coerce it to the async driver so the app doesn't crash on startup.
            value = value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_test(self) -> bool:
        return self.ENVIRONMENT == "test"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (avoids re-parsing env on every call)."""
    return Settings()
