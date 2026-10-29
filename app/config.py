from functools import lru_cache
from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # Database (PostgreSQL 18 / TimescaleDB on Neon)
    DATABASE_URL: str = (
        "postgresql+asyncpg://neondb_owner:your_password_here@ep-ancient-art-b5mstl4r-pooler.c-7.us-east-2.aws.neon.tech/neondb?ssl=require"
    )
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis (Cache & Queue Broker)
    REDIS_URL: str = "redis://localhost:6379/0"

    # Direct API protection. Uses the socket peer; forwarded headers are not trusted here.
    API_RATE_LIMIT_ENABLED: bool = True
    API_RATE_LIMIT_PER_MINUTE: int = Field(default=120, gt=0)
    API_RATE_LIMIT_BURST: int = Field(default=200, gt=0)

    # Supabase Auth
    SUPABASE_URL: str = "https://example.supabase.co"
    SUPABASE_JWT_SECRET: str = "test-jwt-secret-key-at-least-32-chars-long"
    SUPABASE_JWKS_URL: str = "https://example.supabase.co/auth/v1/.well-known/jwks.json"

    # Asaas v3 Billing
    ASAAS_API_KEY: str = "test_asaas_api_key"
    ASAAS_ENVIRONMENT: Literal["sandbox", "production"] = "sandbox"
    ASAAS_WEBHOOK_SECRET: str = "test_webhook_secret"

    # Scrapers & Ingestion
    SCRAPER_USER_AGENT_ROTATION: bool = True
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    CIRCUIT_BREAKER_RECOVERY_TIME_SECONDS: int = 600
    ARQ_MAX_JOBS: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()
