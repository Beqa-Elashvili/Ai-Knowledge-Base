import pytest
from pydantic import ValidationError

from app.config import Settings


def test_defaults() -> None:
    settings = Settings(_env_file=None)  # ignore local .env overrides
    assert (settings.chunk_size, settings.chunk_overlap) == (1600, 200)
    assert settings.max_upload_size_bytes == 20 * 1024 * 1024


def test_invalid_chunk_settings_fail_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHUNK_SIZE", "400")
    monkeypatch.setenv("CHUNK_OVERLAP", "300")
    with pytest.raises(ValidationError, match="CHUNK_OVERLAP"):
        Settings()


def test_supabase_url_must_be_https(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "http://insecure.example.com")
    with pytest.raises(ValidationError, match="https"):
        Settings()


def test_secrets_are_masked_in_repr() -> None:
    assert "test-service-key" not in repr(Settings())
