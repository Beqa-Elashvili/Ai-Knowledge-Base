"""Application configuration loaded from environment variables / .env."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_EMBEDDING_MODELS = {
    "gemini": "gemini-embedding-2",
    "openai": "text-embedding-3-small",
}


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

    # Embeddings. EMBEDDING_MODEL empty = the provider's default model.
    embedding_provider: Literal["gemini", "openai"] = "gemini"
    embedding_model: str = ""
    embedding_batch_size: int = Field(default=100, ge=1)

    # Vector search: chunks returned per question, and the minimum cosine
    # similarity (0-1) a chunk needs to be returned at all.
    search_top_k: int = Field(default=5, ge=1, le=50)
    search_min_similarity: float = Field(default=0.0, ge=0.0, le=1.0)

    # Chat model (Gemini). LLM_THINKING_LEVEL only applies to models that
    # think (e.g. gemini-3.5-flash); empty = the model's default.
    llm_model: str = "gemini-3.5-flash-lite"
    llm_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    llm_max_output_tokens: int = Field(default=2048, ge=64)
    llm_thinking_level: Literal["", "minimal", "low", "medium", "high"] = ""

    # RAG: maximum characters of document excerpts sent to the model.
    rag_max_context_chars: int = Field(default=12000, ge=1000)

    # Summaries: max characters of document text (or notes) per LLM request.
    summary_section_chars: int = Field(default=60000, ge=2000)

    # Suggested questions: how many, and max characters of document text
    # (summary + evenly spread excerpts) they are generated from.
    questions_count: int = Field(default=6, ge=1, le=15)
    questions_source_chars: int = Field(default=30000, ge=2000)

    # Chat memory: earlier messages sent with each question, and the cap on
    # each one's length.
    chat_history_messages: int = Field(default=6, ge=0, le=50)
    chat_history_message_chars: int = Field(default=2000, ge=200)

    # AI provider keys
    gemini_api_key: SecretStr | None = None
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

    @property
    def resolved_embedding_model(self) -> str:
        return self.embedding_model.strip() or DEFAULT_EMBEDDING_MODELS[self.embedding_provider]

    @property
    def embedding_api_key(self) -> SecretStr | None:
        key = self.gemini_api_key if self.embedding_provider == "gemini" else self.openai_api_key
        return key if key and key.get_secret_value().strip() else None


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from the environment
