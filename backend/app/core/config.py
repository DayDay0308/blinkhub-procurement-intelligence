from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from environment variables (12-factor)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "BlinkHub Procurement Intelligence API"
    environment: str = "local"  # local | test | staging | production
    database_url: str = "postgresql+psycopg://blinkhub:blinkhub@localhost:5432/blinkhub"

    jwt_secret: str = Field(default="local-dev-secret-change-me-0123456789", min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60

    cors_origins: list[str] = ["http://localhost:5173"]

    # Business rules (defaults; MICS-specific values to be confirmed)
    payment_terms_days: int = 30
    sla_warning_days: int = 20
    sla_escalation_days: int = 25
    match_tolerance_pct: float = 2.0  # 3-way match tolerance
    bank_change_cooldown_hours: int = 72  # who changed bank details can't pay within this window

    redis_url: str = "redis://localhost:6379/0"
    sla_check_minutes: int = 15
    data_encryption_key: str = "local-dev-data-key-change-me"
    # Supplier compliance documents
    document_dir: str = "/tmp/blinkhub-documents"  # Docker: a named volume; AWS: S3 (Phase 6)
    document_max_mb: int = 5
    compliance_warning_days: int = 30  # "expiring soon" window for certificates

    @model_validator(mode="after")
    def no_default_secret_outside_local(self):
        if self.environment not in ("local", "test") and self.jwt_secret.startswith("local-dev"):
            raise ValueError("Set a real JWT_SECRET outside local/test environments.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
