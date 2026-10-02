"""Test configuration: isolate tests from real credentials and services."""

import os

# Environment variables take precedence over backend/.env, so tests never
# use real Supabase or AI provider credentials.
os.environ.update(
    {
        "SUPABASE_URL": "https://test-project.supabase.co",
        "SUPABASE_SERVICE_KEY": "test-service-key",
        "DATABASE_URL": "postgresql+psycopg://postgres:test@localhost:5432/postgres",
        "EMBEDDING_PROVIDER": "gemini",
        "EMBEDDING_MODEL": "",
        "GEMINI_API_KEY": "test-gemini-key",
        "OPENAI_API_KEY": "test-openai-key",
    }
)
