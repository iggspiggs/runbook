from __future__ import annotations

import logging
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/runbook"

    # Anthropic
    ANTHROPIC_API_KEY: str = ""

    # Security
    SECRET_KEY: str = "change-me-before-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8  # 8 hours

    # CORS — accepts a comma-separated string or a JSON array in the env var
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Environment
    ENV: str = "dev"  # dev | staging | prod

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v  # type: ignore[return-value]

    @property
    def is_production(self) -> bool:
        return self.ENV == "prod"

    def log_safe_summary(self) -> dict:
        """Return config values safe to write to application logs (no secrets)."""
        return {
            "ENV": self.ENV,
            "DATABASE_URL": self.DATABASE_URL.split("@")[-1] if "@" in self.DATABASE_URL else "***",
            "CORS_ORIGINS": self.CORS_ORIGINS,
            "ACCESS_TOKEN_EXPIRE_MINUTES": self.ACCESS_TOKEN_EXPIRE_MINUTES,
            "ANTHROPIC_API_KEY": "set" if self.ANTHROPIC_API_KEY else "NOT SET",
            "SECRET_KEY": "set" if self.SECRET_KEY != "change-me-before-production" else "DEFAULT — change before prod",
        }


settings = Settings()
