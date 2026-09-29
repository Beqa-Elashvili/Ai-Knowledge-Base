"""Application configuration loaded from environment variables / .env."""

from functools import lru_cache

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "AI Knowledge Base API"
    app_version: str = "0.1.0"
    environment: str = "development"
    cors_origins: list[str] = ["http://localhost:3000"]

    # Supabase (backend-only). Secrets are SecretStr so they never appear
    # in logs, reprs or error messages.
    supabase_url: str
    supabase_service_key: SecretStr
    database_url: SecretStr

    # Storage / uploads
    storage_bucket: str = "documents"
    max_upload_size_mb: int = 20
    max_pdf_pages: int = 2000
    signed_url_expires_seconds: int = 3600

    # Chunking (characters)
    chunk_size: int = 1600
    chunk_overlap: int = 200

    # OpenAI — not used until the embeddings phase.
    openai_api_key: SecretStr | None = None

    @field_validator("supabase_url")
    @classmethod
    def _validate_supabase_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith("https://"):
            raise ValueError("SUPABASE_URL must start with https://")
        return value

    @model_validator(mode="after")
    def _validate_chunking(self) -> "Settings":
        if self.chunk_size < 100:
            raise ValueError("CHUNK_SIZE must be at least 100")
        if not 0 <= self.chunk_overlap < self.chunk_size // 2:
            raise ValueError("CHUNK_OVERLAP must be >= 0 and less than half of CHUNK_SIZE")
        return self

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from the environment
