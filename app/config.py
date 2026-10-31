from functools import lru_cache
from typing import Literal
from pydantic import Field, model_validator
from ipaddress import ip_network
from urllib.parse import urlsplit
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = True
    PORT: int = 8000
    HOST: str = "0.0.0.0"

    # Database (PostgreSQL 18 / TimescaleDB on Neon)
    DATABASE_URL: str = Field(default=(
        "postgresql+asyncpg://fin_api_rw@127.0.0.1:5432/fin"
    ), repr=False)
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis (Cache & Queue Broker)
    REDIS_URL: str = Field(default="redis://localhost:6379/0", repr=False)

    # Exact browser origins, including previews only when explicitly configured.
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000", "http://127.0.0.1:3000",
        "https://fin-web.vercel.app", "https://fin-web-wheat.vercel.app",
        "https://fin.com.br", "https://app.fin.com.br",
    ]
    TRUSTED_PROXY_CIDRS: list[str] = []

    # Forwarded headers are accepted only from explicitly trusted peers.
    API_RATE_LIMIT_ENABLED: bool = True
    API_RATE_LIMIT_PER_MINUTE: int = Field(default=120, gt=0)
    API_RATE_LIMIT_BURST: int = Field(default=200, gt=0)

    # Supabase Auth
    SUPABASE_URL: str = "https://example.supabase.co"
    SUPABASE_JWT_SECRET: str = Field(default="test-jwt-secret-key-at-least-32-chars-long", repr=False)
    SUPABASE_JWKS_URL: str = "https://example.supabase.co/auth/v1/.well-known/jwks.json"

    DIRECTUS_URL: str = ""
    DIRECTUS_API_TOKEN: str = Field(default="", repr=False)
    CMS_WEBHOOK_SECRET: str = Field(default="", repr=False)

    BILLING_ENABLED: bool = False

    # Asaas v3 Billing
    ASAAS_API_KEY: str = Field(default="test_asaas_api_key", repr=False)
    ASAAS_ENVIRONMENT: Literal["sandbox", "production"] = "sandbox"
    ASAAS_WEBHOOK_SECRET: str = Field(default="test_webhook_secret", repr=False)

    # Scrapers & Ingestion
    SCRAPER_USER_AGENT_ROTATION: bool = True
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    CIRCUIT_BREAKER_RECOVERY_TIME_SECONDS: int = 600
    ARQ_MAX_JOBS: int = 20

    @model_validator(mode="after")
    def validate_network_policy(self):
        for origin in self.CORS_ORIGINS:
            parsed = urlsplit(origin)
            if (parsed.scheme not in ("https", "http") or not parsed.hostname
                    or parsed.path or parsed.query or parsed.fragment or "*" in origin
                    or parsed.username or parsed.password):
                raise ValueError("CORS origins must be exact HTTP(S) origins")
            if self.ENVIRONMENT == "production" and parsed.scheme != "https":
                raise ValueError("Production CORS origins require HTTPS")
        for cidr in self.TRUSTED_PROXY_CIDRS:
            ip_network(cidr)
        if self.ENVIRONMENT == "production":
            db = urlsplit(self.DATABASE_URL)
            if not db.hostname or db.username in {"avnadmin", "neondb_owner", "postgres"} or any(
                marker in self.DATABASE_URL.lower() for marker in ("your_password", "placeholder", "example.")
            ):
                raise ValueError("Production requires a dedicated non-administrator database role")
            if self.DEBUG:
                raise ValueError("Production requires DEBUG=false")
            if self.BILLING_ENABLED and any(
                not value or value.startswith(("test_", "your-"))
                for value in (self.ASAAS_API_KEY, self.ASAAS_WEBHOOK_SECRET)
            ):
                raise ValueError("Enabled production billing requires explicit provider secrets")
        return self

    @model_validator(mode="after")
    def require_production_jwt_secret(self):
        if self.ENVIRONMENT == "production" and (
            self.SUPABASE_JWT_SECRET == "test-jwt-secret-key-at-least-32-chars-long"
            or len(self.SUPABASE_JWT_SECRET.encode("utf-8")) < 32
        ):
            raise ValueError("Production requires an explicitly configured JWT secret of at least 32 bytes")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
