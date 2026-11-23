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
    document_bucket: str = ""  # set on AWS: files go to this S3 bucket instead of document_dir
    compliance_warning_days: int = 30  # "expiring soon" window for certificates
    # AI features. Without a key, certificate reading uses PDF text rules and Ask BlinkHub
    # uses fixed question templates. With a key, both use the model below.
    anthropic_api_key: str = ""
    ai_model: str = "claude-haiku-5-5"
    ai_timeout_seconds: float = 30.0
    # Ask BlinkHub runs generated SQL on this separate, read-only database login
    ask_db_password: str = "ask-local-dev-password"
    ask_max_rows: int = 200

    @model_validator(mode="after")
    def no_default_secret_outside_local(self):
        if self.environment not in ("local", "test"):
            defaults = {
                "JWT_SECRET": self.jwt_secret.startswith("local-dev"),
                "DATA_ENCRYPTION_KEY": self.data_encryption_key.startswith("local-dev"),
                "ASK_DB_PASSWORD": self.ask_db_password.startswith("ask-local-dev"),
            }
            if any(defaults.values()):
                names = ", ".join(k for k, v in defaults.items() if v)
                raise ValueError(f"Set real values for {names} outside local/test environments.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
